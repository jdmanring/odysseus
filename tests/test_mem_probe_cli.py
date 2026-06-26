"""Smoke test for the mem-probe diagnostic CLI (does not need the live app).

mem-probe.py is the read-only memory/CPU diagnostic for the Qt wrapper; this just
guards that the CLI is wired (argparse builds, all subcommands present) so a
refactor can't silently break the tool. The actual measurements require a running
app on the CDP port and are exercised manually.
"""
import subprocess
import sys
from pathlib import Path

_TOOL = Path(__file__).resolve().parents[1] / "tooling" / "mem-probe.py"


def test_tool_exists():
    assert _TOOL.is_file()


def test_help_lists_all_subcommands():
    r = subprocess.run([sys.executable, str(_TOOL), "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for cmd in ("counters", "slope", "animations", "raf", "mutations", "producers", "purge", "stack"):
        assert cmd in r.stdout, f"subcommand {cmd} missing from --help"


def test_stack_runs_without_cdp():
    """`stack` is a pure /proc reader — it must not require the CDP port, so it
    works even when the app (or its debug port) is down. It should exit 0 and
    print the header regardless of what is running."""
    r = subprocess.run([sys.executable, str(_TOOL), "stack"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "PSS" in r.stdout and "PRIV" in r.stdout


def test_stack_does_not_build_cdp():
    """Guard that main() short-circuits `stack` before constructing CDP (which
    would try to open a socket to the debug port)."""
    src = _TOOL.read_text(encoding="utf-8")
    assert 'if args.cmd == "stack":' in src
    assert "cmd_stack(None, args)" in src


def test_only_purge_mutates_state():
    """Read-only-by-design is the tool's core safety property. The source must not
    clear/pause/cancel page state in any read-only command (those destabilize a
    live session); the only deliberate mutation is forciblyPurge in `purge`."""
    src = _TOOL.read_text(encoding="utf-8")
    for forbidden in ("clearInterval", "clearTimeout", ".cancel()", ".pause()", "classList.add"):
        assert forbidden not in src, f"mem-probe must not call {forbidden} (it must stay read-only)"
    assert "forciblyPurgeJavaScriptMemory" in src  # the one deliberate reclaim, in `purge`
