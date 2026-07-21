"""Behavioral: HfUrlResolver must distinguish a failed listing from an empty repo.

Regression for the false-success download bug: when HuggingFace 429-rate-limits
every listing method (the default with no HF token), resolve_snapshot_urls used
to return an empty list, which the downloader reported as DOWNLOAD_OK. A total
listing failure must raise so the caller emits a real error; a listing that
succeeds but genuinely matches nothing must still return an empty list.
"""
import pytest

from tooling.hf_url_resolver import HfUrlResolver


class _FakeApi:
    """Stand-in for HfApi: each listing method either raises or returns paths."""

    def __init__(self, tree_exc=None, files_exc=None, files=None, token=None):
        self._tree_exc = tree_exc
        self._files_exc = files_exc
        self._files = files or []
        self.token = token

    def list_repo_tree(self, repo_id, recursive=True):
        if self._tree_exc:
            raise self._tree_exc
        return []  # succeeds, no sized items -> falls through to list_repo_files

    def list_repo_files(self, repo_id):
        if self._files_exc:
            raise self._files_exc
        return list(self._files)


def _resolver(**kw):
    r = HfUrlResolver.__new__(HfUrlResolver)
    r.api = _FakeApi(**kw)
    return r


def test_all_listing_methods_failing_raises(monkeypatch):
    # Force the raw-API fallback to also fail so no method succeeds.
    import tooling.hf_url_resolver as mod

    def _boom(*a, **k):
        raise RuntimeError("429 Too Many Requests")

    monkeypatch.setattr(mod.requests, "get", _boom)
    monkeypatch.setattr(HfUrlResolver, "get_commit_hash", lambda self, repo: "main")

    r = _resolver(
        tree_exc=RuntimeError("429 Too Many Requests"),
        files_exc=RuntimeError("429 Too Many Requests"),
    )
    with pytest.raises(RuntimeError, match="could not list files"):
        r.resolve_snapshot_urls("bartowski/Qwen2.5-3B-GGUF")


def test_successful_but_empty_listing_returns_empty(monkeypatch):
    # list_repo_tree succeeds (empty) and list_repo_files succeeds (empty):
    # a genuinely empty match must NOT raise — it returns an empty url list.
    monkeypatch.setattr(HfUrlResolver, "get_commit_hash", lambda self, repo: "abc123")
    r = _resolver(files=[])
    urls, commit = r.resolve_snapshot_urls("some/empty-repo")
    assert urls == [] and commit == "abc123"


def test_successful_listing_returns_urls(monkeypatch):
    monkeypatch.setattr(HfUrlResolver, "get_commit_hash", lambda self, repo: "deadbeef")
    r = _resolver(files=["model.gguf", "config.json"])
    urls, commit = r.resolve_snapshot_urls("some/repo")
    paths = sorted(p for _u, p, _s in urls)
    assert paths == ["config.json", "model.gguf"]
    assert all(commit in u for u, _p, _s in urls)
