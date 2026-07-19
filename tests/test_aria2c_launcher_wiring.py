"""Regression guard for issue #146: the aria2c launcher must stay wired.

The aria2c execution path was silently lost twice:
  - 88e1e123 deleted the _dl_base assignment (NameError on every aria2c run)
  - 247a2a35 amputated the whole launch block instead of fixing it
leaving a pre-flight that flipped a flag nothing read, while every download
silently ran hf_transfer. These are source-level wiring assertions so any
future refactor that drops a piece of the path fails loudly.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROUTES = (REPO / "routes" / "cookbook_routes.py").read_text(encoding="utf-8")
DOWNLOAD_JS = (REPO / "static" / "js" / "cookbookDownload.js").read_text(encoding="utf-8")
RUNNING_JS = (REPO / "static" / "js" / "cookbookRunning.js").read_text(encoding="utf-8")


def test_dl_base_is_assigned_before_use():
    """88e1e123 regression: _dl_base must be assigned, not just referenced."""
    assert "_dl_base = (req.local_dir.rstrip" in ROUTES
    assert ROUTES.index("_dl_base = (req.local_dir.rstrip") < ROUTES.index(
        "_bash_squote(_dl_base)"
    )


def test_launcher_builds_aria2c_command():
    """247a2a35 regression: the launch block must exist and run the script."""
    assert '"tooling" / "aria2c_download.py"' in ROUTES
    assert "hf_cmd = f\"{_py_local} {_bash_squote(_aria2c_script)}" in ROUTES


def test_preflight_precedes_command_build():
    """The pre-flight fallback must run before hf_cmd is chosen, so a flip
    to use_aria2c=False actually selects the hf path."""
    preflight = ROUTES.index("from tooling.aria2c_download import get_aria2c")
    build = ROUTES.index('"tooling" / "aria2c_download.py"')
    assert preflight < build


def test_aria2c_path_skips_retry_loop():
    """aria2c owns resume (.aria2 sidecars); C-c pause exits non-zero and an
    outer retry loop would restart a paused download 30s later."""
    assert ROUTES.count("aria2c handles resume via .aria2 sidecar files") >= 2


def test_remote_runner_uses_scpd_tooling_path():
    """Remote hosts must invoke the scp'd copy, not the server-local path."""
    assert "~/.cookbook/tooling/aria2c_download.py" in ROUTES
    assert 'scp -O {_pf}-q -r tooling {remote}:~/.cookbook/' in ROUTES


def test_no_platform_gate_remains():
    """aria2c runs on every platform now: remote Windows via the .ps1 runner,
    local native-Windows via Git Bash with the server's own interpreter.
    Availability is the get_aria2c() pre-flight's job, not a platform gate."""
    assert "req.use_aria2c and IS_WINDOWS and not req.remote_host" not in ROUTES
    assert 'req.platform == "windows" or (IS_WINDOWS' not in ROUTES
    assert "_py_local = Path(sys.executable).as_posix() if IS_WINDOWS else \"python3\"" in ROUTES


def test_windows_remote_runs_aria2c_via_ps1():
    """Issue #147: the Windows-remote .ps1 runner has a real aria2c branch that
    invokes the scp'd tooling copy with the guest's python."""
    assert '.cookbook\\\\tooling\\\\aria2c_download.py' in ROUTES
    assert "scp -O {_Pf}-q -r tooling {remote}:.cookbook/" in ROUTES
    # Guest deps for the URL resolver are ensured before the run:
    assert 'python -c "import requests, huggingface_hub" 2>$null' in ROUTES
    # aria2c command comes before the generated runner is written to disk:
    assert ROUTES.index("_aria2c_ps_cmd = (") < ROUTES.index('$null | {_aria2c_ps_cmd}')


def test_windows_launch_is_child_owned_redirect():
    """Start-Process -RedirectStandardOutput is pumped by the PARENT shell;
    the ssh shell exits right after launch, the pump dies, and logs stay
    0 bytes. The launch must use WMI Win32_Process.Create with cmd /c owning
    the > redirection in the child (verified live on win11, issue #147)."""
    assert "Invoke-CimMethod -ClassName Win32_Process -MethodName Create" in ROUTES
    dl_block = ROUTES[ROUTES.index("Windows remote: generate .ps1 runner"):
                      ROUTES.index("Linux/Termux remote: create tmux session")]
    assert "-RedirectStandardOutput (" not in dl_block  # the dead parent-pumped form
    # Dollars must stay escaped from the local create_subprocess_shell sh:
    assert "\\\\$sd = Join-Path \\\\$env:TEMP odysseus-sessions" in dl_block


def test_ps1_runner_has_no_doubled_braces():
    """ps_lines are written verbatim (no .format). Doubled braces wrote literal
    {{ }} into the .ps1, turning block bodies into never-invoked scriptblock
    literals — the whole hf runner was a silent no-op."""
    win_block = ROUTES[ROUTES.index("Windows remote: generate .ps1 runner"):
                       ROUTES.index("Linux/Termux remote: create tmux session")]
    for bad in ("'try {{", "{{ Write-Host", "}} else {{", "'}} catch {{"):
        assert bad not in win_block, f"doubled brace regression: {bad!r}"


def test_response_reports_actual_path():
    """The client stores the server's post-preflight decision on the task so
    cookbookRunning.js selects the matching output parser."""
    assert '"use_aria2c": bool(req.use_aria2c and not is_ollama_download)' in ROUTES
    assert "payload.use_aria2c = !!data.use_aria2c" in DOWNLOAD_JS
    assert "use_aria2c: !!data.use_aria2c" in RUNNING_JS
