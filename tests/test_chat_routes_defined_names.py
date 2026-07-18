"""Undefined-name guard for routes/chat_routes.py.

A refactor removed the assignment of `_explicit_web_intent` but left three
reads behind, so every POST /api/chat_stream raised NameError at runtime.
py_compile cannot catch this (NameError is a runtime error) and the module's
policy tests are static AST checks that never execute the route, so the
breakage shipped silently.

This guard closes the class, not just the instance: using stdlib `symtable`,
every name a function reads as an implicit global must actually exist at
module level or in builtins. Zero dependencies, no server needed.
"""
import builtins
import symtable
from pathlib import Path

import pytest

_CHAT_ROUTES = Path(__file__).resolve().parent.parent / "routes" / "chat_routes.py"


def _undefined_global_reads(source: str, filename: str):
    """(scope_name, name) pairs where a function reads a global that is
    bound neither at module level nor in builtins."""
    top = symtable.symtable(source, filename, "exec")
    module_names = {s.get_name() for s in top.get_symbols()}
    known = module_names | set(dir(builtins))
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


def test_chat_routes_has_no_undefined_global_reads():
    bad = _undefined_global_reads(_CHAT_ROUTES.read_text(encoding="utf-8"),
                                  "chat_routes.py")
    assert not bad, (
        f"names read as globals but never defined (runtime NameError): {bad}"
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


def test_detector_accepts_module_level_and_builtin_names():
    src = (
        "LIMIT = 5\n"
        "def handler(n):\n"
        "    return min(n, LIMIT)\n"
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
