"""Backend contract tests for the paginated history endpoint.

`GET /api/history/{session_id}` (routes/history/history_routes.py) is the load-bearing
backend for the fork's scroll-up virtualization: the whole `_fetchOlderFromServer`
paging feature rests on its `limit`/`offset`/`has_more_before`/`has_more_after` math and
on its hidden-row / inline-base64 stripping. Prior to this file that math was exercised at
exactly one point (a single `?limit=24` call in the Playwright render-paging test) and the
hidden/base64 stripping in the *paginated* branch had no behavioral coverage at all — only a
static grep of the separate in-memory fallback branch.

These tests drive the real handler against a real (temporary) SQLite database so the
pagination arithmetic and content stripping are verified as behavior, not asserted as
source strings. Auth is bypassed (single-user/dev semantics) by stubbing the owner check;
the DB session factory is pointed at the seeded temp engine.
"""
import re
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import routes.history.history_routes as history_routes
from core.database import Base, Session as DbSession, ChatMessage as DbChatMessage

PAGE_SID = "page-session"
STRIP_SID = "strip-session"
N_PAGE = 250
BIG_IMAGE = "data:image/png;base64," + ("A" * 300_000)  # over the 200k inline-media threshold


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    db_path = tmp_path_factory.mktemp("history_contract") / "app.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    db = TestingSessionLocal()
    try:
        t = datetime(2026, 1, 1)
        db.add(DbSession(id=PAGE_SID, name="Page", endpoint_url="http://localhost/v1",
                         model="test-model", owner=None))
        for i in range(N_PAGE):
            db.add(DbChatMessage(id=str(uuid.uuid4()), session_id=PAGE_SID,
                                 role="user" if i % 2 == 0 else "assistant",
                                 content=f"SEQMSG {i:04d}", timestamp=t + timedelta(seconds=i)))

        db.add(DbSession(id=STRIP_SID, name="Strip", endpoint_url="http://localhost/v1",
                         model="test-model", owner=None))
        # 0: plain visible, 1: hidden (must be excluded but still counted in total),
        # 2: inline-base64 (bytes must be stripped from the display copy).
        db.add(DbChatMessage(id=str(uuid.uuid4()), session_id=STRIP_SID, role="user",
                             content="visible one", timestamp=t))
        db.add(DbChatMessage(id=str(uuid.uuid4()), session_id=STRIP_SID, role="assistant",
                             content="compaction summary", meta_data='{"hidden": true}',
                             timestamp=t + timedelta(seconds=1)))
        db.add(DbChatMessage(id=str(uuid.uuid4()), session_id=STRIP_SID, role="user",
                             content="here is a picture " + BIG_IMAGE,
                             timestamp=t + timedelta(seconds=2)))
        db.commit()
    finally:
        db.close()

    # Point the route's DB factory at the seeded engine and bypass the owner check.
    orig_local = history_routes.SessionLocal
    orig_verify = history_routes._verify_session_owner
    history_routes.SessionLocal = TestingSessionLocal
    history_routes._verify_session_owner = lambda *a, **k: None

    class _DummySM:
        def get_session(self, sid):
            raise KeyError(sid)

    app = FastAPI()
    app.include_router(history_routes.setup_history_routes(_DummySM()))
    try:
        yield TestClient(app)
    finally:
        history_routes.SessionLocal = orig_local
        history_routes._verify_session_owner = orig_verify
        engine.dispose()


def _get(client, sid, **params):
    r = client.get(f"/api/history/{sid}", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def test_default_offset_is_last_page(client):
    d = _get(client, PAGE_SID, limit=24)
    assert d["total"] == N_PAGE
    assert d["limit"] == 24
    assert d["offset"] == N_PAGE - 24          # default offset = max(total - limit, 0)
    assert len(d["history"]) == 24
    assert d["has_more_before"] is True
    assert d["has_more_after"] is False        # last page: offset + len == total
    assert d["history"][-1]["content"] == f"SEQMSG {N_PAGE - 1:04d}"


def test_first_page_has_more_after_not_before(client):
    d = _get(client, PAGE_SID, limit=24, offset=0)
    assert d["offset"] == 0
    assert d["has_more_before"] is False
    assert d["has_more_after"] is True
    assert d["history"][0]["content"] == "SEQMSG 0000"


def test_middle_page_has_more_both_directions(client):
    d = _get(client, PAGE_SID, limit=24, offset=100)
    assert d["has_more_before"] is True
    assert d["has_more_after"] is True         # 100 + 24 < 250


def test_limit_capped_at_100(client):
    d = _get(client, PAGE_SID, limit=500)
    assert d["limit"] == 100                    # hard cap
    assert d["offset"] == N_PAGE - 100          # default offset uses the capped limit
    assert len(d["history"]) == 100


def test_offset_beyond_total_is_clamped(client):
    d = _get(client, PAGE_SID, limit=24, offset=99999)
    assert d["offset"] == N_PAGE                 # clamped to total
    assert d["history"] == []
    assert d["has_more_after"] is False
    assert d["has_more_before"] is True


def test_hidden_row_excluded_but_counted(client):
    d = _get(client, STRIP_SID, limit=100, offset=0)
    assert d["total"] == 3                       # hidden row still counts toward total
    contents = [m["content"] for m in d["history"]]
    assert "compaction summary" not in contents  # hidden row not returned
    assert len(d["history"]) == 2


def test_inline_base64_stripped_from_display_copy(client):
    d = _get(client, STRIP_SID, limit=100, offset=0)
    img_msg = [m for m in d["history"] if m["role"] == "user" and "picture" in m["content"]]
    assert img_msg, "image message should be present"
    body = img_msg[0]["content"]
    assert "data:image/" not in body            # raw base64 bytes stripped
    assert "omitted from history view" in body


# --- route-shadowing guards (#125) -----------------------------------------
# A legacy GET /api/history/{sid} on the *sessions* router shadowed the paginated
# handler on the history router (FastAPI dispatches to the first-registered match),
# so the paginated endpoint was dead and scroll-up paging never activated. These
# guards fail if the paginated handler stops being the single owner of that path or
# if the legacy handler is reintroduced on the sessions router.

def test_exactly_one_paginated_history_route():
    router = history_routes.setup_history_routes(None)
    matches = [
        r for r in router.routes
        if getattr(r, "path", None) == "/api/history/{session_id}"
        and "GET" in getattr(r, "methods", set())
    ]
    assert len(matches) == 1
    assert matches[0].endpoint.__name__ == "get_session_history"


def test_sessions_router_registers_no_history_get():
    # The sessions router must not re-declare a GET on /history/{...}; doing so would
    # shadow the paginated endpoint again. session_routes.py:748 documents the removal.
    src = Path(__file__).resolve().parent.parent.joinpath("routes/session_routes.py").read_text()
    assert not re.search(r"@router\.get\(\s*[\"']/history", src), \
        "legacy GET /history handler reintroduced on the sessions router — it shadows the paginated route"
