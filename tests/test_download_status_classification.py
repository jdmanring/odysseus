"""Behavioral: the download status classifier the detached poller relies on.

The file-based poller (used for detached downloads on macOS/Windows) resolves a
finished download from the runner's DOWNLOAD_OK / DOWNLOAD_FAILED markers via
classify_dead_download. These are real function-behavior tests (not source
assertions), so the completed/error/running mapping the UI shows is pinned.
"""
from routes.cookbook_output import classify_dead_download


def test_download_ok_is_completed():
    assert classify_dead_download("...\nDONE\nDOWNLOAD_OK\n") == ("completed", False)


def test_download_failed_is_error():
    assert classify_dead_download("boom\nDOWNLOAD_FAILED (exit 1)\n") == ("error", False)


def test_fetching_zero_files_is_error_even_with_ok():
    # A run that matched nothing (bad include/quant) is a failure despite OK.
    status, zero = classify_dead_download("Fetching 0 files: 0it\nDOWNLOAD_OK\n")
    assert status == "error" and zero is True


def test_no_marker_returns_none_for_cache_probe_fallback():
    assert classify_dead_download("just some progress 42%\n") is None
    assert classify_dead_download("") is None


def test_ok_precedence_over_incidental_error_text():
    # aria2c prints benign "[ERROR] ... aborted" mid-run; only the final marker
    # decides. A snapshot ending OK is completed.
    snap = "[ERROR] CUID#7 Download aborted errorCode=22\nDOWNLOAD_OK\n"
    assert classify_dead_download(snap) == ("completed", False)
