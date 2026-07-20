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
    assert "hf_cmd = f\"{_py_local} '{_bash_squote(_aria2c_script)}'" in ROUTES


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


def test_empty_token_never_reaches_hf_api():
    """An empty --token '' produced a literal "Authorization: Bearer " header
    ("Illegal header value"), silently degrading resolution to the unauthenticated
    raw-API fallback. Both the launcher and the resolver must coerce '' to None."""
    from tooling.hf_url_resolver import HfUrlResolver
    assert HfUrlResolver(token="").api.token is None
    launcher = (REPO / "tooling" / "aria2c_download.py").read_text(encoding="utf-8")
    assert "HfUrlResolver(token=args.token or None)" in launcher


def test_download_card_css_exists():
    """4f962b55 ("css render performance pass") deleted the entire download-card
    stylesheet: with no [data-dl-phase] visibility rules, the card rendered the
    "Download complete" AND "Download failed" banners simultaneously while a
    download was still running. Every dl-card class the JS template emits must
    have a stylesheet rule, and the phase gate must exist."""
    css = (REPO / "static" / "style.css").read_text(encoding="utf-8")
    for cls in (".dl-card", ".dl-done-banner", ".dl-error-banner",
                ".dl-phase-progress", ".dl-file-row", ".dl-action-btn"):
        assert cls in css, f"{cls} missing from style.css"
    assert '.dl-card[data-dl-phase="done"]' in css, "phase visibility rules missing"
    assert ".dl-error-banner { display: none; }" in css.replace("\n", " ") or \
           ".dl-error-banner { display: none; }" in css, "banners must be hidden by default"


def test_aria2c_success_markers_are_sentinel_only_everywhere():
    """aria2c output contains '/snapshots/' (the launcher's "Saving to:" line)
    and per-file "Download complete" lines from the first progress tick, so
    those markers are ambient noise, never proof of success. Every site that
    judges a download done must gate the loose markers on the run NOT being
    aria2c — including tasks adopted from the server with no use_aria2c flag,
    which is why detection goes through _isAria2cRun (payload OR output
    fingerprint), not payload.use_aria2c alone."""
    assert "function _isAria2cRun(task)" in RUNNING_JS
    assert "[*] Using aria2c:" in RUNNING_JS  # output fingerprint fallback
    # reconnect heuristic, strong-done finalizer, and self-heal guard all use it
    assert RUNNING_JS.count("_isAria2cRun(") >= 4
    assert "!_isAria2cRun(task) && lastOutput.includes('/snapshots/')" in RUNNING_JS
    assert "_isAria2cRun(t)" in RUNNING_JS  # _selfHealStaleTasks skip-guard


def test_aria2c_bash_args_are_single_quoted():
    """_bash_squote escapes embedded quotes but does NOT wrap the value.
    Used bare, a local-dir containing a space word-splits into bogus argv and
    an include glob like *.gguf is expanded by bash in the tmux session cwd.
    Every value interpolated into the bash aria2c command must be wrapped in
    real single quotes at the call site."""
    assert "f\"--repo '{_bash_squote(req.repo_id)}' \"" in ROUTES
    assert "f\"'{_bash_squote(req.hf_token)}'\" if req.hf_token" in ROUTES
    assert "f\"'{_bash_squote(req.include)}'\" if req.include" in ROUTES
    assert "f\"'{_bash_squote(_dl_base)}'\" if _dl_base" in ROUTES
    assert "'{_bash_squote(_aria2c_script)}'" in ROUTES


def test_launch_scan_cache_is_invalidated_on_mutation():
    """The Launch list renders from a localStorage scan snapshot with a 6-hour
    TTL. Without invalidation on mutation, a deleted model stayed listed and a
    completed download never appeared (verified live: 49-min-old snapshot
    holding only a deleted model while two real models sat on disk). The
    invalidator must exist and be wired to delete-success and to every
    download-completion site."""
    serve_js = (REPO / "static" / "js" / "cookbookServe.js").read_text(encoding="utf-8")
    assert "export function _invalidateCachedModelScan()" in serve_js
    # delete path: invalidate + fresh refetch (not another cached render)
    assert serve_js.count("_invalidateCachedModelScan()") >= 2
    assert "await _fetchCachedModels(true);" in serve_js
    # every download-done site in the running-tab module drops the snapshot
    assert RUNNING_JS.count("_invalidateCachedModelScan?.()") >= 3
    # delete must judge the command's exit_code, not the HTTP status
    assert "_delResult.exit_code !== 0" in serve_js


def test_stylesheet_cache_buster_bumped_with_css_changes():
    """style.css is served under a HARD-CODED ?v= pin in index.html; any CSS
    change is invisible to every client until the pin is bumped. Rule: bump
    the v-param in the same commit as (or after) any style.css change. This
    compares last-commit times of the two files — if style.css is newer than
    index.html, a CSS change shipped without a bump."""
    import subprocess
    def _last_commit_ts(path):
        out = subprocess.run(
            ["git", "log", "-1", "--format=%ct", "--", path],
            capture_output=True, text=True, cwd=REPO,
        ).stdout.strip()
        return int(out) if out else 0
    css_ts = _last_commit_ts("static/style.css")
    html_ts = _last_commit_ts("static/index.html")
    assert css_ts <= html_ts, (
        "static/style.css was committed after static/index.html — if the CSS "
        "change is user-visible, bump the style.css ?v= pin in index.html "
        "(clients never refetch the stylesheet otherwise)"
    )
