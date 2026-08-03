"""Construct a file-backed temp sqlite DB for tests, and remove it afterwards.

Only builds the SQLAlchemy objects from the repeated temp-sqlite block. It does
not patch modules or own any global state beyond the cleanup registry below --
the caller keeps the returned objects alive and binds ``SessionLocal`` where
needed.

Cleanup runs at interpreter exit rather than in a fixture because these
databases are created at module import time, assigned to module globals, and
shared by every test in their file. That is outside any fixture's scope, so
``atexit`` is the mechanism that actually fits; ``tmp_path_factory`` cannot see
an import-time allocation.

DEFER(a CI run is killed rather than exiting): atexit does not run on SIGKILL or
a hard crash, so a killed run still leaves its databases behind. A conftest
session-finish hook would not help (it runs at exit too); covering that case
needs an external sweep, which is not worth standing machinery until a killed
run is actually a recurring problem.
"""
import atexit
import os
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

# Paths handed out by temp_db_file/temp_db_path, removed at interpreter exit.
_TEMP_DB_PATHS = []


def _unlink_db(path):
    """Remove a sqlite database and the WAL/SHM sidecars it may have spawned."""
    for p in (path, path + "-wal", path + "-shm", path + "-journal"):
        try:
            os.unlink(p)
        except OSError:
            pass


def _cleanup_temp_dbs():
    while _TEMP_DB_PATHS:
        _unlink_db(_TEMP_DB_PATHS.pop())


atexit.register(_cleanup_temp_dbs)


def temp_db_file(suffix=".db"):
    """A ``NamedTemporaryFile(delete=False)`` whose path is removed at exit.

    Drop-in for the ``tempfile.NamedTemporaryFile(suffix=".db", delete=False)``
    idiom repeated across the test suite: the caller keeps using ``.name`` and
    keeps the object alive, but the file no longer outlives the run.
    """
    tmpfile = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    _TEMP_DB_PATHS.append(tmpfile.name)
    return tmpfile


def temp_db_path(suffix=".db"):
    """A closed temp database path, removed at exit.

    For callers that only want the path (the ``mkstemp`` idiom) and bind it into
    ``DATABASE_URL`` rather than holding a file object.
    """
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    _TEMP_DB_PATHS.append(path)
    return path


def make_temp_sqlite(metadata):
    """Build a file-backed temp sqlite database and create its tables.

    Returns ``(SessionLocal, engine, tmpfile)``. The caller must keep these
    references alive and bind ``SessionLocal`` onto whatever module the code
    under test reads. The temp file is removed at interpreter exit.
    """
    tmpfile = temp_db_file()
    engine = create_engine(
        f"sqlite:///{tmpfile.name}",
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal, engine, tmpfile
