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
    assert "_shellExecFailure(_delResult)" in serve_js  # behavioral predicate, tested in downloader_behavior.test.mjs


def test_resolve_gguf_endpoint_exists():
    """The /api/cookbook/resolve-gguf route was silently lost from develop
    during the June restorations (the resolver library and the client caller
    both survived, so every GGUF discovery quietly 404'd and the UI showed
    'No GGUF source is configured'). The client, the endpoint, and the
    resolver method must all exist together."""
    assert '@router.get("/api/cookbook/resolve-gguf")' in ROUTES
    assert "find_gguf_sources" in ROUTES
    dl_js = (REPO / "static" / "js" / "cookbookDownload.js").read_text(encoding="utf-8")
    assert "/api/cookbook/resolve-gguf" in dl_js
    from tooling.hf_url_resolver import HfUrlResolver
    assert callable(getattr(HfUrlResolver, "find_gguf_sources", None))


def test_js_behavioral_suite_passes():
    """Runs the node behavioral tests (real aria2c transcripts through the
    extracted parser/state functions). String guards pin that fixes exist;
    this pins that they BEHAVE. Skips only if node is unavailable."""
    import shutil
    import subprocess
    node = shutil.which("node")
    if not node:
        import pytest
        pytest.skip("node not available")
    res = subprocess.run(
        [node, "--test", str(REPO / "tests" / "js" / "downloader_behavior.test.mjs")],
        capture_output=True, text=True, timeout=60,
    )
    assert res.returncode == 0, f"node behavioral tests failed:\n{res.stdout[-3000:]}{res.stderr[-2000:]}"


def test_hf_transfer_is_structurally_dead():
    """hf_transfer is deliberately unsupported (it crashes near the end of
    large files at high throughput; aria2c is the fast path, the plain Python
    downloader is the fallback). No code path may install it or enable it —
    this guard makes reintroduction a visible test failure, not a review
    judgment call."""
    helpers = (REPO / "routes" / "cookbook_helpers.py").read_text(encoding="utf-8")
    shell = (REPO / "routes" / "shell_routes.py").read_text(encoding="utf-8")
    for name, text in [("cookbook_routes.py", ROUTES), ("cookbook_helpers.py", helpers),
                       ("shell_routes.py", shell)]:
        assert "HF_HUB_ENABLE_HF_TRANSFER=1" not in text, f"{name} enables hf_transfer"
        assert 'HF_HUB_ENABLE_HF_TRANSFER = "1"' not in text, f"{name} enables hf_transfer (PS)"
        assert "pip install -q hf_transfer" not in text, f"{name} installs hf_transfer"
        assert "huggingface_hub hf_transfer" not in text, f"{name} installs hf_transfer"
        assert "disable_hf_transfer" not in text, f"{name} resurrects the dead knob"
    for js in ("cookbookDownload.js", "cookbookRunning.js"):
        text = (REPO / "static" / "js" / js).read_text(encoding="utf-8")
        assert "disable_hf_transfer" not in text, f"{js} sends the dead knob"
    # The package panel must not offer it either.
    assert '"pip": "hf_transfer"' not in shell, "package panel offers hf_transfer"


def test_empty_scan_results_are_never_cached():
    """An empty scan is what a Launch refresh races into during delete/download
    mutations; caching [] at the 6-hour TTL hid a freshly downloaded model
    (observed live 2026-07-20). _writeCachedModelScan must drop empty results."""
    serve_js = (REPO / "static" / "js" / "cookbookServe.js").read_text(encoding="utf-8")
    write_fn = serve_js.split("function _writeCachedModelScan", 1)[1].split("\nfunction ", 1)[0]
    assert "data.models.length === 0) return" in write_fn, \
        "empty scan results must not be persisted to the snapshot cache"


def test_auth_pill_has_persistence_and_payload_fallback():
    """The '[*] HF auth:' header prints once and scrolls out of the 500-line
    capture window on fast downloads; the pill must survive via the persisted
    task._authStatus (first poll) with a payload fallback."""
    assert "function _authStatusForTask" in RUNNING_JS
    assert "_updateTask(task.sessionId, { _authStatus: st.authStatus })" in RUNNING_JS
    assert "_authStatusForTask(task, _dlState?.authStatus, _dlState?.phase)" in RUNNING_JS


def test_launcher_diagnoses_gated_repo_auth_failures():
    # Valid token + per-file 401s = gated-repo signature (file lists are
    # public on gated repos; only content needs approved access). The
    # launcher must say so instead of leaving a bare aria2c exit code.
    src = (Path(__file__).parent.parent / "tooling" / "aria2c_download.py").read_text()
    assert "errorCode=24" in src and "GATED" in src
    assert "accept the" in src and "request access" in src


def test_auth_pill_renders_unknown_instead_of_nothing():
    # An absent pill is indistinguishable from a broken one. Tasks with no
    # auth evidence (predating the hf_token_used marker) must render an
    # explicit unknown state.
    js = (Path(__file__).parent.parent / "static" / "js" / "cookbookRunning.js").read_text()
    fn = js[js.index("function _buildAuthPillHtml"):]
    fn = fn[:fn.index("\nfunction ")]
    assert "return '';" not in fn, "empty-auth path renders nothing again"
    assert "auth ?" in fn


def test_launch_response_carries_authoritative_hf_auth():
    # The token is usually attached server-side from stored settings; the
    # client cannot answer "did this download authorize?" from its own
    # payload. The launch response must say so, and the client must persist
    # it into the pill's fallback field.
    server = (Path(__file__).parent.parent / "routes" / "cookbook_routes.py").read_text()
    assert '"hf_auth": bool(req.hf_token)' in server
    client = (Path(__file__).parent.parent / "static" / "js" / "cookbookDownload.js").read_text()
    assert "payload.hf_token_used = !!data.hf_auth" in client


def test_client_live_capture_joins_wrapped_lines():
    # The reconnect loop runs its own tmux capture for the download card's
    # phase parser. Without -J, multi-KB signed-URL lines wrap into dozens of
    # physical rows and flood the capture window, evicting the short phase
    # markers — the card then spins "Initializing…" while the header badge
    # (fed by the server's already-fixed -J capture) shows real progress.
    assert "capture-pane -t ${task.sessionId} -p -J -S -500" in RUNNING_JS, (
        "client live capture lost -J; wrapped URL lines will break phase parsing"
    )


def test_auth_pill_infers_authed_from_reached_download_phase():
    # The wrapper prints "[*] HF auth: authenticated" once, at the top; aria2c's
    # URL flood evicts it from the capture window before the first poll, so the
    # pill stalled yellow at "token…" for the whole download. aria2c only ever
    # starts after a successful token-backed resolve, so downloading/done +
    # token-sent IS authentication evidence.
    fn = RUNNING_JS[RUNNING_JS.index("function _authStatusForTask"):]
    fn = fn[:fn.index("\nfunction ")]
    assert "phase === 'downloading'" in fn and "'authenticated'" in fn, (
        "pill no longer infers authed from token + reached download phase"
    )
    assert "_authStatusForTask(task, st.authStatus, st.phase)" in RUNNING_JS


def test_retry_backend_pinning_semantics():
    """P2-2: aria2c and hf write different disk layouts; a silent backend
    switch on a retry orphans the partials the retry was meant to resume.
    Pinned + unavailable must FAIL LOUDLY, never fall back."""
    from routes.cookbook_helpers import resolve_download_backend, ModelDownloadRequest

    # fresh request, aria2c present: use it
    assert resolve_download_backend(True, False, True) == (True, None)
    # fresh request, aria2c missing: silent fallback is fine (no partials yet)
    use, err = resolve_download_backend(True, False, False)
    assert (use, err) == (False, None)
    # pinned retry, aria2c missing: refuse — never switch layouts
    use, err = resolve_download_backend(True, True, False)
    assert use is True and err and "orphan" in err
    # pinned retry, aria2c present: proceed normally
    assert resolve_download_backend(True, True, True) == (True, None)
    # aria2c never requested: pin is irrelevant
    assert resolve_download_backend(False, True, False) == (False, None)

    # the request model accepts the flag (stale clients simply omit it)
    assert ModelDownloadRequest(repo_id="a/b").pin_backend is False
    assert ModelDownloadRequest(repo_id="a/b", pin_backend=True).pin_backend is True

    # route consumes the helper and refuses on error
    route_src = (Path(__file__).parent.parent / "routes" / "cookbook_routes.py").read_text()
    assert "resolve_download_backend(" in route_src
    assert '"error": _pin_err' in route_src or 'return {"ok": False, "error": _pin_err}' in route_src

    # client pins on retries of a known-aria2c run
    assert "_payload.pin_backend = true" in RUNNING_JS


def test_running_tab_renders_on_tab_switch():
    """Cards created while another tab was up are built with
    _isRunningTabVisible() false, so _reconnectTask never attaches and the
    download card freezes on "Initializing…" while only the header badge
    moves (live repro 2026-07-20, session 861f99f5). Switching to the
    Running tab must re-render so the stream attaches."""
    cookbook = (Path(__file__).parent.parent / "static" / "js" / "cookbook.js").read_text()
    handler = cookbook[cookbook.index("body.querySelectorAll('.cookbook-tab').forEach(tab =>"):]
    handler = handler[:handler.index("Mobile: swipe")]
    assert "backend === 'Running'" in handler and "_renderRunningTab()" in handler, (
        "tab switch to Running no longer re-renders — reconnect loops won't attach"
    )
