"""Edit/regenerate/fork must address the cut point by DB message id, not by an
array/DOM position (#169).

`keep_count` was an absolute index into the timestamp-ordered DB history, but
the client derived it from `indexOf('.msg')` — a DOM-position count that diverges
from the DB index under pagination, dropped synthetic "Continue…" turns, and
multi-bubble agent replies. These tests pin the id-based server primitives and
the precondition that paginated history carries `_db_id`.
"""
import asyncio
import atexit
import importlib
import os
import tempfile
from types import SimpleNamespace

from core.models import ChatMessage


# Each call makes a fresh database; without this they accumulate in /tmp for the
# life of the machine, which matters where /tmp is a RAM-backed tmpfs.
_TEMP_DBS = []


@atexit.register
def _remove_temp_dbs():
    for path in _TEMP_DBS:
        for p in (path, path + "-wal", path + "-shm", path + "-journal"):
            try:
                os.unlink(p)
            except OSError:
                pass


def _make_manager():
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(db_fd)
    _TEMP_DBS.append(db_path)
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    import core.database as database
    importlib.reload(database)
    database.Base.metadata.create_all(bind=database.engine)
    import core.session_manager as sm_mod
    importlib.reload(sm_mod)
    return sm_mod.SessionManager(), database


def _seed(sm, sid):
    sm.create_session(session_id=sid, name="t", endpoint_url="x",
                      model="m", rag=False, owner="u")
    # A realistic history whose array positions do NOT line up with a naive DOM
    # count: includes a synthetic "Continue…" turn (dropped from render) and a
    # multi-round assistant reply (rendered as several bubbles).
    sm.add_message(sid, ChatMessage("user", "keep A"))
    sm.add_message(sid, ChatMessage("assistant", "keep B"))
    sm.add_message(sid, ChatMessage("user", "Continue where you left off"))
    sm.add_message(sid, ChatMessage("user", "cut here"))      # <- target
    sm.add_message(sid, ChatMessage("assistant", "gone C"))
    sm.add_message(sid, ChatMessage("user", "gone D"))
    return sm.sessions[sid].history


def test_truncate_from_message_cuts_target_and_everything_after():
    sm, database = _make_manager()
    sid = "s1"
    history = _seed(sm, sid)
    target_id = history[3].metadata["_db_id"]  # "cut here"

    assert sm.truncate_from_message(sid, target_id) is True

    db = database.SessionLocal()
    try:
        rows = (db.query(database.ChatMessage)
                .filter(database.ChatMessage.session_id == sid)
                .order_by(database.ChatMessage.timestamp).all())
        assert [r.content for r in rows] == ["keep A", "keep B", "Continue where you left off"]
        db_session = db.query(database.Session).filter(database.Session.id == sid).first()
        assert db_session.message_count == 3
    finally:
        db.close()

    # In-memory history filtered by the same id set (target + after gone).
    assert [m.content for m in sm.sessions[sid].history] == [
        "keep A", "keep B", "Continue where you left off"]


def test_truncate_from_message_unknown_id_is_noop():
    sm, database = _make_manager()
    sid = "s2"
    _seed(sm, sid)

    assert sm.truncate_from_message(sid, "does-not-exist") is False

    db = database.SessionLocal()
    try:
        n = (db.query(database.ChatMessage)
             .filter(database.ChatMessage.session_id == sid).count())
        assert n == 6  # nothing deleted
    finally:
        db.close()


def test_paginated_history_stamps_db_id():
    """Precondition: the paginated /history response must carry _db_id so
    scrolled-back / windowed messages remain addressable by id."""
    sm, database = _make_manager()
    sid = "s3"
    _seed(sm, sid)

    import routes.history.history_routes as hr
    importlib.reload(hr)

    router = hr.setup_history_routes(sm)
    endpoint = next(r.endpoint for r in router.routes
                    if getattr(r, "path", "") == "/api/history/{session_id}"
                    and "GET" in getattr(r, "methods", set()))
    # bypass owner check
    hr._verify_session_owner = lambda *a, **k: None

    result = asyncio.run(endpoint(request=SimpleNamespace(), session_id=sid, limit=100, offset=0))
    msgs = result["history"]
    assert msgs, "history should not be empty"
    for m in msgs:
        assert (m.get("metadata") or {}).get("_db_id"), \
            f"paginated history message missing _db_id: {m}"


def _fork_handler(router):
    for route in router.routes:
        if "/fork" in getattr(route, "path", "") and "POST" in getattr(route, "methods", set()):
            return route.endpoint
    raise AssertionError("fork route not found")


class _FakeSession:
    def __init__(self, name="", owner=None):
        self.name = name
        self.owner = owner
        self.endpoint_url = ""
        self.model = ""
        self.history = []

    def add_message(self, message):
        if message.metadata is None:
            message.metadata = {}
        message.metadata.setdefault("_db_id", f"new-{len(self.history)}")
        self.history.append(message)


class _FakeSessionManager:
    def __init__(self, source):
        self.sessions = {"src-id": source}
        self.created = None

    def create_session(self, session_id=None, name=None, endpoint_url=None,
                       model=None, rag=False, owner=None):
        self.created = _FakeSession(name=name, owner=owner)
        return self.created

    def save_sessions(self):
        pass


def test_fork_through_msg_id_copies_up_to_and_including_target(monkeypatch):
    import routes.history_routes as mod
    monkeypatch.setattr(mod, "_verify_session_owner", lambda *a, **k: None)

    source = _FakeSession(name="Original", owner="alice")
    source.history = [
        ChatMessage("user", "u0", {"_db_id": "src-0"}),
        ChatMessage("assistant", "a1", {"_db_id": "src-1"}),   # <- fork through here
        ChatMessage("user", "u2", {"_db_id": "src-2"}),
        ChatMessage("assistant", "a3", {"_db_id": "src-3"}),
    ]
    sm = _FakeSessionManager(source)

    req = SimpleNamespace()

    async def _json():
        return {"through_msg_id": "src-1"}
    req.json = _json

    router = mod.setup_history_routes(sm)
    fork = _fork_handler(router)
    result = asyncio.run(fork(request=req, session_id="src-id"))

    assert result["status"] == "ok"
    # Copied up to and including a1 (src-1); u2/a3 excluded.
    assert [m.content for m in sm.created.history] == ["u0", "a1"]


# ── client: the edit/regenerate/fork sites must send the DB id, not keep_count ──

import pathlib


def test_client_sends_id_based_truncate_and_fork_payloads():
    src = (pathlib.Path(__file__).resolve().parent.parent / "static/js/chat.js").read_text()
    # Three truncate sites (editUserMessage, resendUserMessage, regenerateFrom)
    # prefer from_msg_id; fork prefers through_msg_id.
    assert src.count("from_msg_id: _dbId") == 3, "edit/resend/regen must send from_msg_id"
    assert src.count("through_msg_id: _dbId") == 1, "fork must send through_msg_id"
    # keep_count remains only as the fallback branch of each ternary.
    assert src.count("keep_count: keepCount") == 4, "keep_count must survive as fallback"
    # The id comes from the clicked element's dataset.dbId.
    assert "userMsgElement.dataset.dbId" in src
    assert "userMsgEl.dataset.dbId" in src
    assert "aiMsgElement.dataset.dbId" in src
