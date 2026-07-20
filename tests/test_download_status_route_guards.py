"""Regression guards for the download status route (2026-07-20 incident).

Two live-download defects shipped together:
1. tmux capture-pane without -J wraps aria2c's 2-3 KB signed-URL NOTICE lines
   into ~80-char fragments — the long-URL filter in error_aware_output_tail
   never matches them, the tail window fills with URL wall, and the client
   loses the progress summary / FILE: lines / auth banner ("initializing"
   forever, no per-file bars).
2. The generic has_error sniff ran before the download-specific branches, so
   aria2c's benign self-retried "[ERROR] CUID#N ... errorCode=22" lines
   classified a healthy live download as crashed.

The status logic lives inside the route closure, so these are source-level
guards; the tier-1 behavioral harness supersedes them when it lands.
"""

import re
from pathlib import Path

SRC = (Path(__file__).parent.parent / "routes" / "cookbook_routes.py").read_text()


def test_all_capture_pane_calls_join_wrapped_lines():
    # Every status/watchdog capture-pane invocation must pass -J.
    for m in re.finditer(r'capture-pane[^\n]*"-S"', SRC):
        line = SRC[SRC.rfind("\n", 0, m.start()) + 1 : SRC.find("\n", m.end())]
        if '"-500"' in line or '"-2000"' in line:
            assert '"-J"' in line, f"capture-pane without -J: {line.strip()}"


def test_download_branches_precede_generic_has_error():
    # In the live-session classifier, DOWNLOAD_OK/FAILED/incomplete evidence
    # must be consulted before the generic "error"/"failed" text sniff.
    block = SRC[SRC.index("elif has_exit and task_type == \"download\""):]
    block = block[: block.index("Parse structured phase info")]
    generic = block.index("elif has_error")
    for marker in ("download_has_ok", "download_has_failed", "download_has_incomplete_evidence"):
        assert block.index(marker) < generic, f"{marker} checked after generic has_error"


def test_generic_has_error_skips_live_downloads():
    assert re.search(
        r'elif has_error and not \(task_type == "download" and is_alive\)', SRC
    ), "generic has_error must not classify a live download"


def test_secret_scrub_preserves_auth_marker():
    assert "hf_token_used" in SRC, "server scrub must keep the non-secret auth marker"
    js = (Path(__file__).parent.parent / "static" / "js" / "cookbookRunning.js").read_text()
    assert js.count("hf_token_used") >= 2, "client must write and read hf_token_used"
