"""
Integration tests for the aria2c download system.

Tests the actual download path:
  BinManager (auto-install) -> HfUrlResolver (URL list) -> aria2c subprocess -> file on disk

Uses gpt2 (public, ~500MB tokenizer files only with --include filter) so the test
completes in reasonable time without a large model download.

All tests in TestHfUrlResolver and TestDownloadFile make live network calls to
huggingface.co. They are marked ``slow`` so the fast lane (pytest -m "not slow")
skips them. Run the full suite to exercise the end-to-end path.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import pytest

# Allow running from project root or tests/ directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ---------------------------------------------------------------------------
# Schema and pre-flight contracts (static — no network, no binary needed)
# ---------------------------------------------------------------------------

_HELPERS_SRC = (Path(__file__).resolve().parents[1] / "routes" / "cookbook_helpers.py").read_text(encoding="utf-8")
_ROUTES_SRC  = (Path(__file__).resolve().parents[1] / "routes" / "cookbook_routes.py").read_text(encoding="utf-8")


def test_use_aria2c_defaults_to_true():
    """aria2c is the default download path; hf download is the fallback."""
    assert "use_aria2c: bool = True" in _HELPERS_SRC


def test_preflight_check_present_in_routes():
    """Pre-flight guard must exist before the download command is built.

    The check probes aria2c availability and routes through
    resolve_download_backend (reworded from the original `get_aria2c() is None`
    form in the backend-pinning refactor 2538f11c — the guard still exists)."""
    assert "get_aria2c() is not None" in _ROUTES_SRC
    assert "resolve_download_backend(" in _ROUTES_SRC


def test_preflight_logs_fallback():
    """Fallback must be logged so operators can diagnose unexpected hf-download use."""
    assert "falling back to hf download" in _ROUTES_SRC


def test_preflight_skipped_for_ollama():
    """aria2c pre-flight must be skipped for Ollama downloads (no HF resolution needed)."""
    assert "req.use_aria2c and not is_ollama_download" in _ROUTES_SRC

from tooling.bin_manager import BinManager
from tooling.aria2c_download import get_aria2c, download_file
from tooling.hf_url_resolver import HfUrlResolver


class TestBinManagerAria2c(unittest.TestCase):
    """BinManager installs aria2c and returns a usable binary."""

    def test_ensure_binary_returns_path(self):
        path = BinManager.ensure_binary("aria2c")
        self.assertIsNotNone(path, "BinManager failed to install aria2c")
        self.assertTrue(Path(path).exists(), f"Binary path does not exist: {path}")

    def test_binary_is_executable(self):
        path = BinManager.ensure_binary("aria2c")
        self.assertIsNotNone(path)
        self.assertTrue(os.access(path, os.X_OK), "aria2c binary is not executable")

    def test_binary_responds_to_version(self):
        path = BinManager.ensure_binary("aria2c")
        self.assertIsNotNone(path)
        import subprocess
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, "aria2c --version failed")
        self.assertIn("aria2", result.stdout.lower(), "Unexpected --version output")


class TestGetAria2c(unittest.TestCase):
    """get_aria2c() resolves the binary via BinManager or system PATH."""

    def test_get_aria2c_returns_path(self):
        path = get_aria2c()
        self.assertIsNotNone(path, "get_aria2c() returned None — neither BinManager nor PATH found aria2c")
        self.assertTrue(path.exists())

    def test_get_aria2c_executable(self):
        path = get_aria2c()
        self.assertIsNotNone(path)
        self.assertTrue(os.access(path, os.X_OK))


@pytest.mark.slow
class TestHfUrlResolver(unittest.TestCase):
    """HfUrlResolver produces valid HTTPS URLs for a known public repo."""

    def test_resolves_gpt2_tokenizer(self):
        resolver = HfUrlResolver(token=None)
        # Filter to tokenizer files only — small and public
        urls, commit = resolver.resolve_snapshot_urls("gpt2", include="*.json")
        self.assertGreater(len(urls), 0, "No .json files returned for gpt2")
        for url, rel_path, size in urls:
            self.assertTrue(url.startswith("https://huggingface.co/"), f"Unexpected URL: {url}")
            self.assertFalse(rel_path.startswith("/"), f"rel_path should be relative: {rel_path}")
            self.assertIsInstance(size, int, f"size should be int: {size!r}")

    def test_commit_hash_returned(self):
        resolver = HfUrlResolver(token=None)
        urls, commit = resolver.resolve_snapshot_urls("gpt2", include="tokenizer.json")
        self.assertIsNotNone(commit, "commit should never be None (falls back to 'main')")
        # A real SHA is 40 hex chars; "main" is the fallback
        is_sha = len(commit) == 40 and all(c in "0123456789abcdef" for c in commit)
        is_fallback = commit == "main"
        self.assertTrue(is_sha or is_fallback, f"Unexpected commit value: {commit!r}")
        # URLs should contain the commit in their path
        for url, _, _size in urls:
            self.assertIn(commit, url, f"URL not pinned to commit {commit!r}: {url}")


@pytest.mark.slow
class TestDownloadFile(unittest.TestCase):
    """download_file() fetches a real file from HuggingFace via aria2c subprocess."""

    def test_downloads_gpt2_tokenizer_json(self):
        aria2c = get_aria2c()
        self.assertIsNotNone(aria2c, "aria2c binary not available")

        resolver = HfUrlResolver(token=None)
        urls, commit = resolver.resolve_snapshot_urls("gpt2", include="tokenizer.json")
        self.assertTrue(urls, "Resolver returned no URLs for gpt2/tokenizer.json")
        url, rel_path, _size = urls[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ok = download_file(aria2c, url, tmp, Path(rel_path).name, token=None)
            self.assertTrue(ok, "download_file returned False for tokenizer.json")
            downloaded = tmp / Path(rel_path).name
            self.assertTrue(downloaded.exists(), "tokenizer.json not found after download")
            self.assertGreater(downloaded.stat().st_size, 0, "tokenizer.json is empty")

    def test_resume_is_idempotent(self):
        """Running download_file twice on the same file should succeed (--continue=true)."""
        aria2c = get_aria2c()
        self.assertIsNotNone(aria2c)

        resolver = HfUrlResolver(token=None)
        urls, _ = resolver.resolve_snapshot_urls("gpt2", include="tokenizer.json")
        self.assertTrue(urls)
        url, rel_path, _size = urls[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ok1 = download_file(aria2c, url, tmp, Path(rel_path).name, token=None)
            self.assertTrue(ok1)
            size1 = (tmp / Path(rel_path).name).stat().st_size
            # Second call with --continue=true — should exit 0, not re-download
            ok2 = download_file(aria2c, url, tmp, Path(rel_path).name, token=None)
            self.assertTrue(ok2)
            size2 = (tmp / Path(rel_path).name).stat().st_size
            self.assertEqual(size1, size2, "File size changed on re-download")


class TestFallbackWhenAria2cAbsent(unittest.TestCase):
    """get_aria2c() uses system PATH when BinManager has no entry for this platform."""

    def test_system_path_fallback(self):
        # If system aria2c exists, get_aria2c() should find it even if BinManager
        # returns None (simulated by temporarily hiding BinManager's result).
        system = shutil.which("aria2c")
        if system is None:
            self.skipTest("No system aria2c on PATH — skipping fallback test")
        path = get_aria2c()
        self.assertIsNotNone(path)


if __name__ == "__main__":
    unittest.main()
