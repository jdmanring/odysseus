"""Shared real-app bootstrap: seed a DB, boot the actual app under uvicorn, tear down.

One tested implementation of the "real server" fixture, extracted from
tests/test_chat_history_render_paging_playwright.py after
tests/bench/network_arm_bench.py grew a duplicate. Every consumer that claims
"measured against the real app" should boot through this module, so the claim
always means the same thing: `import app` (the full FastAPI app), a real
SQLite DB, real HTTP on 127.0.0.1.

Consumers own their corpus: pass `seed` as a callable(db_url) or use
seed_session() for the common one-session shape.
"""
import os
import pathlib
import signal
import socket
import statistics
import subprocess
import time
import urllib.request
import uuid
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def seed_session(db_url: str, sid: str, contents, name: str = "Bench Session",
                 model: str = "bench-model") -> None:
    """Create one session holding `contents` (list of message strings; roles
    alternate user/assistant by index, timestamps strictly increasing)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from core.database import Base, Session as DbSession, ChatMessage as DbChatMessage

    engine = create_engine(db_url)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        db.add(DbSession(id=sid, name=name, endpoint_url="http://localhost/v1",
                         model=model, owner=None))
        t = datetime(2026, 1, 1)
        for i, content in enumerate(contents):
            db.add(DbChatMessage(id=str(uuid.uuid4()), session_id=sid,
                                 role="user" if i % 2 == 0 else "assistant",
                                 content=content, timestamp=t + timedelta(seconds=i)))
        db.commit()
    finally:
        db.close()


class LiveApp:
    """The real app, running. `seed` is a callable(db_url) that populates the DB
    before boot. Use as a context manager or call stop() yourself."""

    def __init__(self, datadir: str, seed):
        self.datadir = datadir
        db_url = f"sqlite:///{datadir}/app.db"
        seed(db_url)
        self.port = free_port()
        env = dict(os.environ)
        env.update({"ODYSSEUS_DATA_DIR": datadir, "DATABASE_URL": db_url,
                    "AUTH_ENABLED": "false", "LOCALHOST_BYPASS": "true",
                    "APP_PORT": str(self.port)})
        self.proc = subprocess.Popen(
            [f"{ROOT}/venv/bin/python", "-c",
             f"import uvicorn, app; uvicorn.run(app.app, host='127.0.0.1', "
             f"port={self.port}, log_level='warning')"],
            cwd=str(ROOT), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.base = f"http://127.0.0.1:{self.port}"
        for _ in range(120):
            try:
                urllib.request.urlopen(self.base + "/", timeout=2)
                return
            except Exception:
                time.sleep(0.5)
        self.stop()
        raise RuntimeError("server did not start")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()

    def stop(self) -> None:
        self.proc.send_signal(signal.SIGTERM)
        try:
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()

    def handler_latency_ms(self, sid: str, offset: int, limit: int = 100,
                           samples: int = 7) -> dict:
        """Server-side page cost with no browser in the loop: time a cold
        /api/history page fetch. Median + spread over samples."""
        vals = []
        for _ in range(samples):
            t0 = time.perf_counter()
            urllib.request.urlopen(
                f"{self.base}/api/history/{sid}?limit={limit}&offset={offset}",
                timeout=10).read()
            vals.append((time.perf_counter() - t0) * 1000.0)
        return {"median_ms": round(statistics.median(vals), 2),
                "spread_ms": round(max(vals) - min(vals), 2)}
