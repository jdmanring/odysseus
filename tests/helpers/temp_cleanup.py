"""Registry for temp files and directories the test suite creates at import time.

Most temp resources in a test belong to pytest's ``tmp_path``/``tmp_path_factory``
fixtures, which clean themselves up and keep the last few runs for debugging. Use
those whenever the allocation happens inside a test or fixture.

This module covers the case the fixtures cannot: a module-level allocation, made
at import time and assigned to a module global that every test in the file shares.
That happens before any fixture exists, so cleanup has to be registered against
interpreter exit instead.

DEFER(a run is killed rather than exiting): ``atexit`` does not run on SIGKILL or
a hard crash, so a killed run still leaves its resources behind. A conftest
session-finish hook would not help, since that runs at exit too. Covering it needs
an external sweep, which is not worth standing machinery until killed runs are
actually a recurring problem.
"""
import atexit
import os
import shutil
import tempfile

# Paths handed out below, removed at interpreter exit.
_TEMP_PATHS = []


def _remove_path(path):
    """Remove a file or directory tree, plus any sqlite sidecars beside it.

    Never raises: this runs during interpreter shutdown, where an exception is
    both useless and noisy.
    """
    for p in (path + "-wal", path + "-shm", path + "-journal"):
        try:
            os.unlink(p)
        except OSError:
            pass
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            os.unlink(path)
    except OSError:
        pass


def _cleanup():
    while _TEMP_PATHS:
        _remove_path(_TEMP_PATHS.pop())


atexit.register(_cleanup)


def register(path):
    """Mark an already-created path for removal at exit. Returns the path."""
    _TEMP_PATHS.append(path)
    return path


def temp_dir(prefix="odysseus-test-"):
    """``mkdtemp`` whose directory is removed at exit.

    For module-level data directories only. Inside a test, use ``tmp_path``.
    """
    return register(tempfile.mkdtemp(prefix=prefix))


def temp_file(suffix="", delete=False):
    """``NamedTemporaryFile(delete=False)`` whose path is removed at exit.

    Returns the file object, so callers keep using ``.name`` unchanged.
    """
    tmpfile = tempfile.NamedTemporaryFile(suffix=suffix, delete=delete)
    register(tmpfile.name)
    return tmpfile


def temp_path(suffix=""):
    """A closed temp file path, removed at exit (the ``mkstemp`` idiom)."""
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return register(path)
