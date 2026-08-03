"""Construct a file-backed temp sqlite DB for tests, and remove it afterwards.

Only builds the SQLAlchemy objects from the repeated temp-sqlite block. It does
not patch modules or own global state -- the caller keeps the returned objects
alive and binds ``SessionLocal`` where needed.

Cleanup is delegated to :mod:`tests.helpers.temp_cleanup`, which removes the
database and its WAL/SHM sidecars at interpreter exit. These databases are
created at module import time and assigned to module globals, which is outside
any fixture's scope, so ``tmp_path_factory`` cannot see them.
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from tests.helpers.temp_cleanup import temp_file, temp_path


def temp_db_file(suffix=".db"):
    """A ``NamedTemporaryFile(delete=False)`` whose path is removed at exit.

    Drop-in for the ``tempfile.NamedTemporaryFile(suffix=".db", delete=False)``
    idiom repeated across the suite: the caller keeps using ``.name`` and keeps
    the object alive, but the file no longer outlives the run.
    """
    return temp_file(suffix=suffix)


def temp_db_path(suffix=".db"):
    """A closed temp database path, removed at exit.

    For callers that only want the path (the ``mkstemp`` idiom) and bind it into
    ``DATABASE_URL`` rather than holding a file object.
    """
    return temp_path(suffix=suffix)


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
