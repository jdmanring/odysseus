"""Undefined-name guard for every module in routes/.

A refactor removed the assignment of `_explicit_web_intent` in
routes/chat_routes.py but left three reads behind, so every POST
/api/chat_stream raised NameError at runtime. Generalizing this guard to the
whole routes/ package immediately found a second instance of the class: the
exception handler in `hf_gguf_files` (routes/cookbook_routes.py) logged an
undefined `repo`, turning the graceful-degradation path into a 500.

py_compile cannot catch either (NameError is a runtime error) and the
modules' policy tests are static AST checks that never execute the routes, so
both shipped silently.

This guard closes the class, not the instances: using stdlib `symtable`,
every name a function reads as an implicit global must actually exist at
module level, in builtins, or among the implicit module globals. Zero
dependencies, no server needed.
"""
import builtins
import symtable
from pathlib import Path

import pytest

_ROUTES_DIR = Path(__file__).resolve().parent.parent / "routes"
_ROUTE_FILES = sorted(_ROUTES_DIR.glob("*.py"))

# Names every module scope gets at runtime without an assignment statement.
_IMPLICIT_MODULE_GLOBALS = {
    "__file__", "__name__", "__doc__", "__package__", "__spec__",
    "__loader__", "__builtins__", "__annotations__", "__cached__",
}


def _undefined_global_reads(source: str, filename: str):
    """(scope_name, name) pairs where a function reads a global that is
    bound neither at module level nor in builtins."""
    top = symtable.symtable(source, filename, "exec")
    module_names = {s.get_name() for s in top.get_symbols()}
    known = module_names | set(dir(builtins)) | _IMPLICIT_MODULE_GLOBALS
    bad = []

    def walk(table):
        for child in table.get_children():
            if child.get_type() == "function":
                for sym in child.get_symbols():
                    if (sym.is_global() and not sym.is_assigned()
                            and sym.get_name() not in known):
                        bad.append((child.get_name(), sym.get_name()))
            walk(child)

    walk(top)
    return bad


def test_route_modules_were_collected():
    assert len(_ROUTE_FILES) > 40, (
        f"expected the routes/ package, found {len(_ROUTE_FILES)} files — "
        "did the layout move?"
    )


@pytest.mark.parametrize("path", _ROUTE_FILES, ids=lambda p: p.name)
def test_route_module_has_no_undefined_global_reads(path):
    bad = _undefined_global_reads(path.read_text(encoding="utf-8"), path.name)
    assert not bad, (
        f"{path.name}: names read as globals but never defined "
        f"(runtime NameError): {bad}"
    )


# The desktop wrappers are the same defect class with a worse blast radius:
# PyQt6 aborts the whole process on an unhandled exception in a slot, so a
# NameError in a timer callback is a hard app crash. windows_wrapper.py
# shipped exactly that (`_cdp_executor` used, never defined — ported from
# qt_wrapper.py without its definition; crashed on first mouse-idle).
_WRAPPER_FILES = [
    p for p in (
        Path(__file__).resolve().parent.parent / name
        for name in ("windows_wrapper.py", "qt_wrapper.py", "mac_wrapper.py")
    ) if p.exists()
]


def test_wrapper_modules_were_collected():
    assert _WRAPPER_FILES, "no desktop wrapper modules found — layout moved?"


@pytest.mark.parametrize("path", _WRAPPER_FILES, ids=lambda p: p.name)
def test_wrapper_module_has_no_undefined_global_reads(path):
    bad = _undefined_global_reads(path.read_text(encoding="utf-8"), path.name)
    assert not bad, (
        f"{path.name}: names read as globals but never defined "
        f"(runtime NameError; PyQt aborts the app on slot exceptions): {bad}"
    )


# --- mutation checks: the guard is only as good as its detector -----------


def test_detector_flags_removed_assignment():
    """The regression shape: definition deleted, read left behind."""
    src = (
        "import os\n"
        "def handler(flag):\n"
        "    if _explicit_web_intent:\n"
        "        return os.getcwd()\n"
    )
    assert _undefined_global_reads(src, "x.py") == [
        ("handler", "_explicit_web_intent")]


def test_detector_flags_typo_of_a_local():
    """The second regression shape: a read that is a typo of a local
    (the `repo` vs `repo_id` case)."""
    src = (
        "def handler(repo_id):\n"
        "    try:\n"
        "        return repo_id\n"
        "    except Exception:\n"
        "        return repo\n"
    )
    assert _undefined_global_reads(src, "x.py") == [("handler", "repo")]


def test_detector_accepts_module_level_and_builtin_names():
    src = (
        "LIMIT = 5\n"
        "def handler(n):\n"
        "    return min(n, LIMIT)\n"
    )
    assert _undefined_global_reads(src, "x.py") == []


def test_detector_accepts_implicit_module_globals():
    src = (
        "def where():\n"
        "    return __file__\n"
    )
    assert _undefined_global_reads(src, "x.py") == []


def test_detector_accepts_local_and_closure_bindings():
    src = (
        "def outer():\n"
        "    bound = 1\n"
        "    def inner():\n"
        "        local = 2\n"
        "        return bound + local\n"
        "    return inner\n"
    )
    assert _undefined_global_reads(src, "x.py") == []
