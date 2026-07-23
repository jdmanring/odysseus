"""App-managed Qdrant server lifecycle.

The vector store defaults to a real Qdrant **server** (the Rust binary) so multiple
processes — the app and the memory MCP subprocess, and multiple remote clients in a
networked deployment — share one concurrent store. This is what the single-writer
embedded/local mode cannot do.

Binary resolution, in order:
  1. `shutil.which("qdrant")` — FreeBSD (pkg) and OpenBSD (built from source) install
     it on PATH; also honours a system/admin-provided binary anywhere.
  2. `BinManager.ensure_binary("qdrant")` — downloads the pinned official static
     release for Linux/macOS/Windows.
  3. None → caller falls back to embedded local mode (e.g. OpenBSD if the build is
     absent).

`ensure_running()` is idempotent and safe across processes: if something already
answers on the port it just returns True (the MCP subprocess thus connects to the
server the app started rather than launching a rival). Only the process that
actually spawned the child owns stopping it (`stop()`), so a connecting process
never reaps the app's server.
"""
from __future__ import annotations

import logging
import os
import shutil
import socket
import subprocess
import time
import urllib.request

logger = logging.getLogger(__name__)

_proc = None            # the child WE launched (None if we only connected)
_resolved_binary = None  # cache the resolved path


def _binary():
    global _resolved_binary
    if _resolved_binary is not None:
        return _resolved_binary or None
    found = shutil.which("qdrant")
    if not found:
        try:
            from tooling.bin_manager import BinManager
            p = BinManager.ensure_binary("qdrant")
            found = str(p) if p else None
        except Exception as e:
            logger.info("Qdrant binary not resolvable via BinManager: %s", e)
            found = None
    _resolved_binary = found or ""   # "" caches "looked, found nothing"
    return found


def _port_responds(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_available(host: str, port: int) -> bool:
    """A server is usable if one is already answering, or we can resolve a binary."""
    return _port_responds(host, port) or bool(_binary())


def ensure_running(host: str, port: int, storage_dir: str) -> bool:
    """Ensure a Qdrant server answers at host:port. Returns True if one is up
    (already running or launched by us), False if no binary is available."""
    global _proc
    if _port_responds(host, port):
        return True                       # someone (maybe our own app) already runs it
    binary = _binary()
    if not binary:
        return False                      # caller falls back to local mode
    os.makedirs(storage_dir, exist_ok=True)
    env = os.environ.copy()
    # Qdrant reads QDRANT__<SECTION>__<KEY> env overrides on top of its built-in
    # defaults, so no config file is needed.
    env["QDRANT__STORAGE__STORAGE_PATH"] = storage_dir
    # Override the snapshots path too: the FreeBSD pkg bakes /var/db/qdrant into
    # its default config, and qdrant panics (PermissionDenied) creating snapshot
    # temp dirs there when run as an ordinary user. Keep everything under our
    # storage dir on every platform.
    env["QDRANT__STORAGE__SNAPSHOTS_PATH"] = os.path.join(storage_dir, "snapshots")
    env["QDRANT__SERVICE__HTTP_PORT"] = str(port)
    # gRPC would otherwise bind its default 6334 no matter what HTTP port we
    # chose, so two instances (e.g. the app's and a test's) would collide.
    env["QDRANT__SERVICE__GRPC_PORT"] = str(port + 1)
    env["QDRANT__SERVICE__HOST"] = host
    env["QDRANT__TELEMETRY_DISABLED"] = "true"
    logger.info("Starting Qdrant server (%s) on %s:%s, storage=%s",
                binary, host, port, storage_dir)
    try:
        _proc = subprocess.Popen(
            [binary],
            env=env,
            cwd=storage_dir,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except Exception as e:
        logger.warning("Qdrant server failed to launch: %s", e)
        _proc = None
        return False
    # Wait for readiness (HTTP /readyz).
    for _ in range(60):                   # up to ~30s cold start
        if _proc.poll() is not None:
            logger.warning("Qdrant server exited during startup (code %s)",
                           _proc.returncode)
            _proc = None
            return False
        try:
            with urllib.request.urlopen(f"http://{host}:{port}/readyz", timeout=1) as r:
                if r.status == 200:
                    logger.info("Qdrant server ready.")
                    return True
        except Exception:
            time.sleep(0.5)
    logger.warning("Qdrant server slow to become ready; proceeding.")
    return _port_responds(host, port)


def stop() -> None:
    """Stop the server only if THIS process launched it."""
    global _proc
    if _proc is None:
        return
    try:
        _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except Exception:
            _proc.kill()
    except Exception:
        pass
    _proc = None
