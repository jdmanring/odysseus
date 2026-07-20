"""Guard: platform wrappers disable uvicorn's per-request access log (issue #113).

uvicorn's access_log defaults to ON, so the embedded launch must pass
--no-access-log explicitly to stop the always-on UI polls from churning
server_access.log forever. Removing the bare --access-log flag is NOT enough
(logging is the default), so this guards that the negative flag is present and
the bare positive flag is gone.
"""
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_WRAPPERS = [p for p in ("qt_wrapper.py", "mac_wrapper.py", "windows_wrapper.py")
             if (_ROOT / p).is_file()]


@pytest.mark.parametrize("wrapper", _WRAPPERS)
def test_wrapper_uses_no_access_log(wrapper):
    src = (_ROOT / wrapper).read_text(encoding="utf-8")
    if "uvicorn" not in src:
        pytest.skip(f"{wrapper} does not launch uvicorn")
    assert '"--no-access-log"' in src, f"{wrapper} must pass --no-access-log"
    assert '"--access-log"' not in src, f"{wrapper} still passes the bare --access-log"


def test_windows_wrapper_spawns_server_without_console():
    """Under pythonw the wrapper has no console; without CREATE_NO_WINDOW the
    console-subsystem python.exe server child pops its own console window."""
    path = _ROOT / "windows_wrapper.py"
    if not path.is_file():
        pytest.skip("windows_wrapper.py not present")
    src = path.read_text(encoding="utf-8")
    assert "subprocess.CREATE_NO_WINDOW" in src, (
        "windows_wrapper.py must spawn the server with CREATE_NO_WINDOW"
    )


def test_windows_wrapper_all_subprocesses_are_console_less():
    """Every subprocess spawn in windows_wrapper.py must pass creationflags
    (CREATE_NO_WINDOW): the 60s tasklist memory poll without it flashed a
    console window over the app once a minute under pythonw."""
    import ast
    path = _ROOT / "windows_wrapper.py"
    if not path.is_file():
        pytest.skip("windows_wrapper.py not present")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess"
                and node.func.attr in ("run", "Popen", "call", "check_output")):
            if not any(k.arg == "creationflags" for k in node.keywords):
                offenders.append(f"line {node.lineno}: subprocess.{node.func.attr}")
    assert not offenders, f"subprocess calls without creationflags: {offenders}"
