"""Boot smoke test — the merged app must load in a real browser without JS errors.

The web UI is 46 ES-module scripts loaded via init.js. Unit tests can't see an
import/syntax/wiring break introduced by an upstream sync (a bad merge that still
parses per-file but fails to initialise the module graph). This boots the real
FastAPI app against a throwaway DB and loads the SPA in Chromium, failing on any
uncaught exception or JS-breakage signature.

Skips cleanly when Playwright or its Chromium build is unavailable (minimal CI).
Asserts only robust signals — uncaught `pageerror` and breakage *signatures* in
the console — never a blanket "zero console.errors", which is noisy.

Run just this file:  venv/bin/python -m pytest tests/test_ui_boot_smoke_playwright.py
"""
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

import pytest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Skip cleanly if Playwright isn't importable.
playwright_api = pytest.importorskip("playwright.sync_api")

# JS-breakage signatures: an out-of-order or broken merge shows up as these.
_BREAKAGE = re.compile(
    r"SyntaxError|is not defined|Cannot use import|Unexpected token|"
    r"Failed to (fetch|load) module|does not provide an export|ReferenceError",
    re.IGNORECASE,
)


def _free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="module")
def app_server():
    """Boot the real app against a throwaway DB; yields the base URL."""
    datadir = tempfile.mkdtemp(prefix="odysseus_ui_smoke_")
    port = _free_port()
    env = dict(os.environ)
    env.update({
        "ODYSSEUS_DATA_DIR": datadir,
        # Set DATABASE_URL pre-import so it wins over .env (load_dotenv doesn't override).
        "DATABASE_URL": f"sqlite:///{datadir}/app.db",
        "AUTH_ENABLED": "false",
        "LOCALHOST_BYPASS": "true",
        "APP_PORT": str(port),
    })
    launcher = (
        "import uvicorn, app; "
        f"uvicorn.run(app.app, host='127.0.0.1', port={port}, log_level='warning')"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", launcher], cwd=_REPO, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        ready = False
        for _ in range(60):  # up to ~30s for cold import + startup
            if proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(base + "/", timeout=2)
                ready = True
                break
            except Exception:
                time.sleep(0.5)
        if not ready:
            pytest.fail(f"app server did not become ready on {base} (exit={proc.poll()})")
        yield base
    finally:
        proc.send_signal(signal.SIGTERM)
        try:
            proc.wait(timeout=10)
        except Exception:
            proc.kill()
        shutil.rmtree(datadir, ignore_errors=True)


@pytest.fixture(scope="module")
def booted_page(app_server):
    from playwright.sync_api import sync_playwright
    try:
        pw = sync_playwright().start()
    except Exception as e:  # pragma: no cover
        pytest.skip(f"Playwright runtime unavailable: {e}")
    try:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception as e:
            pytest.skip(f"Chromium not installed for Playwright: {e}")
        page = browser.new_context(viewport={"width": 1280, "height": 900}).new_page()
        errors = {"pageerror": [], "console_error": []}
        page.on("pageerror", lambda e: errors["pageerror"].append(str(e)))
        page.on("console", lambda m: errors["console_error"].append(m.text) if m.type == "error" else None)
        page.goto(app_server + "/", wait_until="networkidle", timeout=30000)
        page.wait_for_selector("#message", timeout=15000)
        yield page, errors
        browser.close()
    finally:
        pw.stop()


def test_core_ui_present(booted_page):
    page, _ = booted_page
    for sel in ("#sidebar", "#chat-history", "#message", "#cookbook-modal"):
        assert page.evaluate(f"!!document.querySelector('{sel}')"), f"missing {sel} after boot"


def test_no_uncaught_js_errors(booted_page):
    _, errors = booted_page
    assert not errors["pageerror"], "uncaught JS exception(s) on boot:\n" + "\n".join(errors["pageerror"][:10])


def test_no_module_breakage_signatures(booted_page):
    _, errors = booted_page
    hits = [e for bucket in errors.values() for e in bucket if _BREAKAGE.search(e)]
    assert not hits, "JS import/syntax/wiring breakage on boot:\n" + "\n".join(hits[:10])


def test_merge_touched_module_imports(booted_page):
    # cookbookRunning.js (reconciled in the merge) must load in the app's real order.
    page, _ = booted_page
    ok = page.evaluate(
        "(async () => { try { const m = await import('/static/js/cookbookRunning.js');"
        " return typeof m._renderRunningTab === 'function'; }"
        " catch (e) { return 'IMPORT_ERR:' + e.message; } })()"
    )
    assert ok is True, f"cookbookRunning.js failed to import in the browser: {ok}"
