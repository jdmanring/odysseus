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


def _load_pick_download_progress():
    m = re.search(
        r"def _pick_download_progress.*?return clean\[-1\] if clean else \"\"", SRC, re.S
    )
    assert m, "_pick_download_progress not found or its shape changed"
    ns = {}
    exec("import re\n" + re.sub(r"^        ", "", m.group(0), flags=re.M), ns)
    return ns["_pick_download_progress"]


def test_progress_picker_never_returns_url_noise():
    # With capture-pane -J, redirect NOTICEs are single 2-3 KB lines; the old
    # lines[-1] fallback put one straight into the card header.
    pick = _load_pick_download_progress()
    notice = "07/20 04:47:36 [NOTICE] CUID#28 - Redirecting to https://us.aws.cdn.hf.co/" + "x" * 2000
    assert pick([notice, notice]) == ""
    assert "http" not in pick(["some line", notice])


def test_progress_picker_prefers_aria2c_compact_line():
    pick = _load_pick_download_progress()
    compact = "[DL:42MiB][#362407 3.0GiB/4.6GiB(66%)][#302381 3.1GiB/4.1GiB(74%)]"
    notice = "07/20 [NOTICE] Redirecting to https://cdn/" + "x" * 300
    assert pick([compact, notice]) == compact
    assert pick(["FILE: /a/b/model-00001-of-00002.safetensors", compact]) == compact


def test_secret_scrub_preserves_auth_marker():
    assert "hf_token_used" in SRC, "server scrub must keep the non-secret auth marker"
    js = (Path(__file__).parent.parent / "static" / "js" / "cookbookRunning.js").read_text()
    assert js.count("hf_token_used") >= 2, "client must write and read hf_token_used"


def test_serve_diagnosis_covers_prestartup_free_memory_check():
    # vLLM refuses to start when desired utilization exceeds actual free VRAM
    # (desktop compositor/shell/app always hold some). All three diagnosis
    # surfaces must recognize it: helpers, the routes-local shadow copy, and
    # the client's clickable-fix table.
    from routes.cookbook_helpers import _diagnose_serve_output
    err = ("ValueError: Free memory on device cuda:0 (13.51/15.59 GiB) on startup "
           "is less than desired GPU memory utilization (0.9, 14.03 GiB).")
    d = _diagnose_serve_output(err)
    assert d and "hold part of the GPU" in d["message"]
    assert any("0.80" in s.get("value", "") for s in d["suggestions"])
    pat = "Free memory on device .* is less than desired GPU memory utilization"
    assert pat in SRC, "routes-local shadow copy missing the pattern"
    js = (Path(__file__).parent.parent / "static" / "js" / "cookbook-diagnosis.js").read_text()
    assert "Free memory on device" in js


def test_serve_diagnosis_covers_missing_nvcc_flashinfer_jit():
    from routes.cookbook_helpers import _diagnose_serve_output
    err = "RuntimeError: Could not find nvcc and default cuda_home='/usr/local/cuda' doesn't exist"
    d = _diagnose_serve_output(err)
    assert d and "nvcc" in d["message"]
    assert "Could not find nvcc and default cuda_home" in SRC
    js = (Path(__file__).parent.parent / "static" / "js" / "cookbook-diagnosis.js").read_text()
    assert "Could not find nvcc" in js


def test_vllm_serve_runner_falls_back_to_native_sampler_without_nvcc():
    # flashinfer JIT-compiles at startup and aborts the engine when nvcc is
    # missing; sampling needs no compiler. The runner must set the fallback
    # for every vLLM launch, not just one model's normalizer.
    idx = SRC.index('elif "vllm serve" in req.cmd:')
    block = SRC[idx : idx + 2500]
    assert "VLLM_USE_FLASHINFER_SAMPLER=0" in block
    assert "/opt/cuda" in block, "Arch-family CUDA_HOME probe missing"


def test_serve_diagnosis_covers_kv_cache_context_ceiling():
    from routes.cookbook_helpers import _diagnose_serve_output
    err = ("ValueError: To serve at least one request with the model's max seq len (40960), "
           "(5.62 GiB KV cache is needed, which is larger than the available KV cache memory (3.06 GiB).")
    d = _diagnose_serve_output(err)
    assert d and "context" in d["message"]
    assert any(s.get("flag") == "--max-model-len" for s in d["suggestions"])
    assert "is larger than the available KV cache memory" in SRC
    js = (Path(__file__).parent.parent / "static" / "js" / "cookbook-diagnosis.js").read_text()
    assert "is larger than the available KV cache memory" in js
