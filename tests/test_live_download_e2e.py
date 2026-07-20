"""Deliberate live E2E tier for the download stack.

Boots its OWN uvicorn instance — temp data dir, internal-token auth, a
download directory confined to the test's temp path — and drives a real tiny
download through the real endpoints: launch -> tmux session -> aria2c ->
status pipeline -> DOWNLOAD_OK -> files on disk.

It never touches the user's running app session or their HF cache (the
ODYSSEUS_LIVE_UI_TESTS lesson: hijacking the live session broke the user's
UI while tests ran). Opt-in because it needs network + tmux + aria2c:

    RUN_LIVE_E2E=1 python -m pytest -m live -q
"""

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

pytestmark = [pytest.mark.live, pytest.mark.slow]

REPO = Path(__file__).parent.parent
TINY_REPO = "hf-internal-testing/tiny-random-gpt2"

if os.environ.get("RUN_LIVE_E2E") != "1":
    pytest.skip("live E2E is opt-in: set RUN_LIVE_E2E=1", allow_module_level=True)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _App:
    def __init__(self, proc, port, token, workdir):
        self.proc = proc
        self.port = port
        self.token = token
        self.workdir = workdir
        self.sessions = []  # tmux session ids we created, for teardown

    def req(self, path, payload=None, timeout=30):
        url = f"http://127.0.0.1:{self.port}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        r = urllib.request.Request(
            url, data=data,
            headers={
                "Content-Type": "application/json",
                "X-Odysseus-Internal-Token": self.token,
            },
        )
        with urllib.request.urlopen(r, timeout=timeout) as resp:
            return json.loads(resp.read().decode())


@pytest.fixture(scope="module")
def live_app(tmp_path_factory):
    workdir = tmp_path_factory.mktemp("live-e2e")
    port = _free_port()
    token = secrets.token_hex(16)
    env = dict(os.environ)
    env.update({
        "ODYSSEUS_DATA_DIR": str(workdir / "data"),
        "ODYSSEUS_INTERNAL_TOKEN": token,
        # never inherit the user's stored settings/token paths implicitly
        "HF_HUB_DISABLE_TELEMETRY": "1",
    })
    (workdir / "data").mkdir(parents=True, exist_ok=True)
    log = open(workdir / "uvicorn.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    app = _App(proc, port, token, workdir)
    try:
        deadline = time.time() + 120
        last_err = None
        while time.time() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(
                    f"app exited rc={proc.returncode}:\n"
                    + (workdir / "uvicorn.log").read_text()[-3000:]
                )
            try:
                app.req("/api/health", timeout=5)
                break
            except Exception as e:  # noqa: BLE001 — readiness probe
                last_err = e
                time.sleep(1.5)
        else:
            raise RuntimeError(f"app never became healthy: {last_err}")
        yield app
    finally:
        for sid in app.sessions:
            subprocess.run(["tmux", "kill-session", "-t", sid],
                           capture_output=True, timeout=10)
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def test_live_download_lifecycle(live_app):
    """launch -> running -> DOWNLOAD_OK -> completed -> files on disk."""
    dl_dir = live_app.workdir / "models"
    dl_dir.mkdir(exist_ok=True)

    data = live_app.req("/api/model/download", {
        "repo_id": TINY_REPO,
        "use_aria2c": True,
        "local_dir": str(dl_dir),
    })
    assert data.get("ok"), f"launch refused: {data}"
    sid = data["session_id"]
    live_app.sessions.append(sid)
    # the response reports the ACTUAL backend after pre-flight
    assert data.get("use_aria2c") is True, (
        "aria2c pre-flight fell back to hf — live tier requires the aria2c path"
    )

    # Task registration is the CLIENT's job (the launch route does not
    # self-register; /api/cookbook/tasks/status only reports tasks present in
    # the cookbook state). Do what the browser's _syncToServer does.
    live_app.req("/api/cookbook/state", {
        "tasks": [{
            "id": sid, "sessionId": sid, "type": "download",
            "status": "running", "name": TINY_REPO,
            "payload": {"repo_id": TINY_REPO, "use_aria2c": True},
            "ts": int(time.time() * 1000),
        }],
    })

    saw_running = False
    final = None
    deadline = time.time() + 300
    while time.time() < deadline:
        tasks = live_app.req("/api/cookbook/tasks/status").get("tasks", [])
        mine = next((t for t in tasks if t.get("session_id") == sid), None)
        if mine:
            if mine.get("status") == "running":
                saw_running = True
            if mine.get("status") in ("completed", "error", "stopped") \
                    or "DOWNLOAD_OK" in (mine.get("output_tail") or ""):
                final = mine
                break
        time.sleep(3)
    assert final is not None, "download never reached a terminal state"

    tail = final.get("output_tail") or ""
    assert "DOWNLOAD_OK" in tail, f"no success sentinel; status={final.get('status')} tail:\n{tail[-1500:]}"
    assert "DOWNLOAD_FAILED" not in tail
    assert saw_running or final.get("status") == "completed"

    # disk truth, confined to the test dir: the flat aria2c layout
    short = TINY_REPO.split("/")[-1]
    landed = list((dl_dir / short).rglob("*"))
    landed_files = [p for p in landed if p.is_file() and p.stat().st_size > 0]
    assert landed_files, f"no files landed under {dl_dir / short}"
    names = {p.name for p in landed_files}
    assert "config.json" in names, f"expected config.json among {sorted(names)[:10]}"


def test_live_status_pipeline_shape(live_app):
    """The status route returns the fields the client state machine consumes."""
    tasks = live_app.req("/api/cookbook/tasks/status").get("tasks", [])
    assert isinstance(tasks, list)
    for t in tasks:
        assert "session_id" in t and "status" in t
        # progress/output_tail may be empty but must exist for download tasks
        if t.get("type") == "download":
            assert "output_tail" in t
