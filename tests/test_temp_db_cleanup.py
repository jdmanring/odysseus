"""The test suite must not leave its sqlite databases behind in /tmp.

Every temp database was created with ``delete=False`` and never unlinked, by 20
test modules and the shared helper. On a developer machine that is a slow leak;
on one where /tmp is a RAM-backed tmpfs it is a real resource loss, and it was
measured at 3,790 files / 2.06 GB accumulated over two weeks, which starved the
Playwright suite of memory until unrelated tests began failing with
"Page crashed".

These tests pin the two properties that keep it fixed: allocation registers the
path, and cleanup actually removes the file and its sqlite sidecars.

Cleanup is exercised through ``_unlink_db`` on this test's own paths rather than
by calling ``_cleanup_temp_dbs``, which would drain the shared registry and
delete databases other test modules in the same process are still using.
"""
import os

from tests.helpers import sqlite_db


def test_temp_db_file_is_registered_for_cleanup():
    f = sqlite_db.temp_db_file()
    try:
        assert os.path.exists(f.name)
        assert f.name in sqlite_db._TEMP_DB_PATHS, (
            "temp_db_file() handed out a path it will never clean up"
        )
    finally:
        sqlite_db._unlink_db(f.name)
        if f.name in sqlite_db._TEMP_DB_PATHS:
            sqlite_db._TEMP_DB_PATHS.remove(f.name)


def test_temp_db_path_is_registered_and_closed():
    path = sqlite_db.temp_db_path()
    try:
        assert os.path.exists(path)
        assert path in sqlite_db._TEMP_DB_PATHS
        # mkstemp's descriptor must already be closed: the caller binds this
        # path into DATABASE_URL and never sees the fd.
        with open(path, "w"):
            pass
    finally:
        sqlite_db._unlink_db(path)
        if path in sqlite_db._TEMP_DB_PATHS:
            sqlite_db._TEMP_DB_PATHS.remove(path)


def test_unlink_removes_wal_and_shm_sidecars():
    """sqlite in WAL mode leaves -wal/-shm next to the database."""
    f = sqlite_db.temp_db_file()
    sqlite_db._TEMP_DB_PATHS.remove(f.name)
    sidecars = [f.name + s for s in ("-wal", "-shm", "-journal")]
    for s in sidecars:
        with open(s, "w") as fh:
            fh.write("x")

    sqlite_db._unlink_db(f.name)

    assert not os.path.exists(f.name)
    for s in sidecars:
        assert not os.path.exists(s), f"{s} survived cleanup"


def test_unlink_is_idempotent_and_survives_a_missing_file():
    """Cleanup runs at interpreter exit; it must never raise there."""
    f = sqlite_db.temp_db_file()
    sqlite_db._TEMP_DB_PATHS.remove(f.name)
    sqlite_db._unlink_db(f.name)
    sqlite_db._unlink_db(f.name)  # second pass must not raise


def test_make_temp_sqlite_registers_its_database():
    """The shared helper is the most-used allocator; it must not opt out."""
    from sqlalchemy import MetaData

    SessionLocal, engine, tmpfile = sqlite_db.make_temp_sqlite(MetaData())
    try:
        assert tmpfile.name in sqlite_db._TEMP_DB_PATHS
    finally:
        engine.dispose()
        sqlite_db._unlink_db(tmpfile.name)
        if tmpfile.name in sqlite_db._TEMP_DB_PATHS:
            sqlite_db._TEMP_DB_PATHS.remove(tmpfile.name)


def test_no_test_module_hand_rolls_a_temp_database():
    """The leak came back once per new test file; this is the guard.

    A new module that writes its own ``NamedTemporaryFile(suffix=".db",
    delete=False)`` reintroduces exactly the defect this change fixed, and
    nothing else in the suite would notice.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent
    offenders = []
    for p in root.rglob("*.py"):
        if p.name == "sqlite_db.py" or p.name == pathlib.Path(__file__).name:
            continue
        body = p.read_text(encoding="utf-8")
        if 'suffix=".db"' in body and "temp_db_" not in body:
            offenders.append(str(p.relative_to(root)))

    assert not offenders, (
        "these modules create a temp database without the shared helper, so it "
        "is never cleaned up; use tests.helpers.sqlite_db.temp_db_file() or "
        f"temp_db_path(): {offenders}"
    )
