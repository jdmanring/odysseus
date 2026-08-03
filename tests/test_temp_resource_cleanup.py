"""The test suite must not leave its temp files or directories behind in /tmp.

Every temp database was created with ``delete=False`` and never unlinked, by 20
test modules and the shared helper. On a developer machine that is a slow leak;
on one where /tmp is a RAM-backed tmpfs it is a real resource loss, and it was
measured at 3,790 files / 2.06 GB accumulated over two weeks, which starved the
Playwright suite of memory until unrelated tests began failing with
"Page crashed".

Measured the same day: 67,496 orphaned directories from module-level mkdtemp,
which dwarfed the database count.

These tests pin the properties that keep it fixed: allocation registers the
path, cleanup removes the file (with its sqlite sidecars) or the whole directory
tree, and no module reintroduces a hand-rolled allocation.

Cleanup is exercised through ``_remove_path`` on this test's own paths rather
than by calling ``_cleanup``, which would drain the shared registry and delete
resources other test modules in the same process are still using.
"""
import os

from tests.helpers import sqlite_db
from tests.helpers import temp_cleanup


def test_temp_db_file_is_registered_for_cleanup():
    f = sqlite_db.temp_db_file()
    try:
        assert os.path.exists(f.name)
        assert f.name in temp_cleanup._TEMP_PATHS, (
            "temp_db_file() handed out a path it will never clean up"
        )
    finally:
        temp_cleanup._remove_path(f.name)
        if f.name in temp_cleanup._TEMP_PATHS:
            temp_cleanup._TEMP_PATHS.remove(f.name)


def test_temp_db_path_is_registered_and_closed():
    path = sqlite_db.temp_db_path()
    try:
        assert os.path.exists(path)
        assert path in temp_cleanup._TEMP_PATHS
        # mkstemp's descriptor must already be closed: the caller binds this
        # path into DATABASE_URL and never sees the fd.
        with open(path, "w"):
            pass
    finally:
        temp_cleanup._remove_path(path)
        if path in temp_cleanup._TEMP_PATHS:
            temp_cleanup._TEMP_PATHS.remove(path)


def test_unlink_removes_wal_and_shm_sidecars():
    """sqlite in WAL mode leaves -wal/-shm next to the database."""
    f = sqlite_db.temp_db_file()
    temp_cleanup._TEMP_PATHS.remove(f.name)
    sidecars = [f.name + s for s in ("-wal", "-shm", "-journal")]
    for s in sidecars:
        with open(s, "w") as fh:
            fh.write("x")

    temp_cleanup._remove_path(f.name)

    assert not os.path.exists(f.name)
    for s in sidecars:
        assert not os.path.exists(s), f"{s} survived cleanup"


def test_unlink_is_idempotent_and_survives_a_missing_file():
    """Cleanup runs at interpreter exit; it must never raise there."""
    f = sqlite_db.temp_db_file()
    temp_cleanup._TEMP_PATHS.remove(f.name)
    temp_cleanup._remove_path(f.name)
    temp_cleanup._remove_path(f.name)  # second pass must not raise


def test_make_temp_sqlite_registers_its_database():
    """The shared helper is the most-used allocator; it must not opt out."""
    from sqlalchemy import MetaData

    SessionLocal, engine, tmpfile = sqlite_db.make_temp_sqlite(MetaData())
    try:
        assert tmpfile.name in temp_cleanup._TEMP_PATHS
    finally:
        engine.dispose()
        temp_cleanup._remove_path(tmpfile.name)
        if tmpfile.name in temp_cleanup._TEMP_PATHS:
            temp_cleanup._TEMP_PATHS.remove(tmpfile.name)


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
        if 'suffix=".db"' not in body:
            continue
        # The helper is the preferred route, but a module that removes its own
        # databases is not a leak. A module that does neither is.
        cleans_up = any(tok in body for tok in
                        ("temp_db_", "temp_path", "os.unlink", "os.remove",
                         "shutil.rmtree", "tmp_path"))
        if not cleans_up:
            offenders.append(str(p.relative_to(root)))

    assert not offenders, (
        "these modules create a temp database and never remove it; use "
        "tests.helpers.sqlite_db.temp_db_file()/temp_db_path(), or clean up "
        f"explicitly: {offenders}"
    )


def test_temp_dir_is_registered_and_removed_with_its_contents():
    """Directory leaks dwarfed the database leak: 67,496 orphaned dirs."""
    d = temp_cleanup.temp_dir(prefix="odysseus-cleanup-test-")
    temp_cleanup._TEMP_PATHS.remove(d)
    with open(os.path.join(d, "a.txt"), "w") as fh:
        fh.write("x")

    temp_cleanup._remove_path(d)

    assert not os.path.exists(d), "temp_dir left a non-empty directory behind"


def test_no_test_module_hand_rolls_a_temp_directory():
    """Module-level mkdtemp must go through the registry.

    An allocation inside a test or fixture belongs to pytest's tmp_path and is
    fine; this only catches the module-level idiom, which no fixture can clean.
    """
    import pathlib as _pathlib
    import re as _re

    root = _pathlib.Path(__file__).resolve().parent
    offenders = []
    for p in root.rglob("*.py"):
        if p.name in ("temp_cleanup.py", _pathlib.Path(__file__).name):
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").split("\n"), 1):
            if _re.match(r"^\w+ = (Path\()?tempfile\.mkdtemp\(", line):
                offenders.append(f"{p.relative_to(root)}:{i}")

    assert not offenders, (
        "module-level mkdtemp is never cleaned up; use "
        f"tests.helpers.temp_cleanup.temp_dir(): {offenders}"
    )
