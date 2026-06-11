"""
chroma_client.py

Singleton ChromaDB HTTP client.
Connects to a ChromaDB instance running as a standalone service.
"""

import os
import socket
import structlog
import time

logger = structlog.get_logger(__name__)

_client = None

# A short connect probe so an unreachable ChromaDB fails fast instead of
# blocking on the OS connection timeout (~30-60s, WinError 10060 on Windows),
# which otherwise stalls app startup. Tunable via CHROMADB_CONNECT_TIMEOUT.
_CONNECT_TIMEOUT = float(os.getenv("CHROMADB_CONNECT_TIMEOUT", "2.0"))


def _port_open(host: str, port: int, timeout: float = None) -> tuple[bool, float]:
    """Return (is_open, elapsed_ms) for a TCP connection to host:port."""
    _t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout or _CONNECT_TIMEOUT):
            return True, (time.monotonic() - _t0) * 1000
    except OSError:
        return False, (time.monotonic() - _t0) * 1000


def get_chroma_client():
    """Get or create the singleton ChromaDB HTTP client.

    Raises RuntimeError with a clear install hint if the `chromadb` package
    is not installed — it's an optional dependency (RAG + memory vectors).
    """
    global _client
    if _client is not None:
        return _client

    try:
        import chromadb
    except ImportError as e:
        raise RuntimeError(
            "ChromaDB integration is not installed. Install the optional "
            "dependency with: pip install chromadb-client"
        ) from e

    host = os.getenv("CHROMADB_HOST", "localhost")
    port = int(os.getenv("CHROMADB_PORT", "8100"))

    is_open, tcp_ms = _port_open(host, port)
    if not is_open:
        raise RuntimeError(
            f"ChromaDB is not reachable at {host}:{port} "
            f"(tcp_probe_ms={tcp_ms:.0f}). Start the ChromaDB "
            f"service (e.g. `docker compose up chromadb`) or set CHROMADB_HOST / "
            f"CHROMADB_PORT to point at a running instance."
        )

    client = chromadb.HttpClient(host=host, port=port)

    # Health check before caching — if the port is open but the service isn't
    # healthy yet (e.g. still starting), don't poison the singleton with a dead
    # client; leave _client unset so the next call retries.
    _hb_start = time.monotonic()
    client.heartbeat()
    _hb_ms = (time.monotonic() - _hb_start) * 1000
    _client = client
    logger.info("chroma_connected", host=host, port=port,
                tcp_ms=round(tcp_ms, 1), heartbeat_ms=round(_hb_ms, 1))
    return _client


def reset_client():
    """Reset the singleton (e.g. after config change)."""
    global _client
    _client = None
