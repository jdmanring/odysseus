"""Tests for get_github_cli_prompt() in src/integrations.py.

The function probes whether the gh CLI is installed and authenticated, then
returns a system prompt block advertising its availability to the agent.

Three guarded paths:
  1. gh not on PATH  →  return ""  (shutil.which guard)
  2. `gh auth status` exits non-zero  →  return ""  (returncode guard)
  3. `gh auth status` raises an exception  →  return ""  (try/except guard)

Tests use monkeypatch to control shutil.which and subprocess.run since those
are OS-boundary calls.  The function imports both inside its body, so patching
the module objects in sys.modules is the right technique — both the test file
and the function share the same module references.
"""
import os
import shutil
import subprocess
from types import SimpleNamespace

import pytest

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
import src.integrations as _integrations_mod
from src.integrations import get_github_cli_prompt


@pytest.fixture(autouse=True)
def _reset_gh_cli_cache():
    """Reset the module-level prompt cache before every test so tests are independent."""
    _integrations_mod._gh_cli_prompt_cache = None
    yield
    _integrations_mod._gh_cli_prompt_cache = None


def _make_proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestGhCliNotInstalled:
    def test_returns_empty_string_when_gh_not_on_path(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: None)
        assert get_github_cli_prompt() == ""

    def test_returns_string_type(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: None)
        result = get_github_cli_prompt()
        assert isinstance(result, str)


class TestGhCliAuthFailure:
    def test_returns_empty_when_auth_status_fails(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **kw: _make_proc(returncode=1, stderr="not authenticated"))
        assert get_github_cli_prompt() == ""

    def test_returns_empty_when_subprocess_raises(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(OSError("no gh")))
        assert get_github_cli_prompt() == ""


class TestGhCliAuthenticated:
    """When gh is installed and authenticated, the function returns a non-empty
    system prompt block."""

    def _auth_run(self, cmd, **kw):
        if "auth" in cmd and "status" in cmd:
            return _make_proc(stdout="Logged in to github.com account testuser (keyring)\n")
        if "auth" in cmd and "token" in cmd:
            return _make_proc(stdout="ghp_testtoken123\n")
        return _make_proc()

    def test_returns_non_empty_string(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run", self._auth_run)
        result = get_github_cli_prompt()
        assert result != ""
        assert isinstance(result, str)

    def test_prompt_mentions_github_cli(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run", self._auth_run)
        result = get_github_cli_prompt()
        assert "GitHub CLI" in result

    def test_prompt_contains_username(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run", self._auth_run)
        result = get_github_cli_prompt()
        assert "testuser" in result

    def test_prompt_contains_example_commands(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run", self._auth_run)
        result = get_github_cli_prompt()
        assert "gh repo list" in result
        assert "gh pr list" in result
        assert "gh issue create" in result

    def test_sets_gh_token_env_when_absent(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run", self._auth_run)
        monkeypatch.delenv("GH_TOKEN", raising=False)
        get_github_cli_prompt()
        assert os.environ.get("GH_TOKEN") == "ghp_testtoken123"

    def test_does_not_overwrite_existing_gh_token(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        monkeypatch.setattr(subprocess, "run", self._auth_run)
        monkeypatch.setenv("GH_TOKEN", "already-set")
        get_github_cli_prompt()
        assert os.environ.get("GH_TOKEN") == "already-set"

    def test_falls_back_to_you_when_username_not_parsed(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)

        def _run_no_username(cmd, **kw):
            if "auth" in cmd and "status" in cmd:
                return _make_proc(stdout="Authentication status: ok\n")
            return _make_proc(stdout="ghp_token\n")

        monkeypatch.setattr(subprocess, "run", _run_no_username)
        result = get_github_cli_prompt()
        assert "you" in result
        assert result != ""


class TestGhCliCache:
    """The module-level cache must ensure subprocess.run is called only once
    across multiple invocations of get_github_cli_prompt()."""

    def _auth_run(self, cmd, **kw):
        if "auth" in cmd and "status" in cmd:
            return _make_proc(stdout="Logged in to github.com account cachetestuser (keyring)\n")
        if "auth" in cmd and "token" in cmd:
            return _make_proc(stdout="ghp_cachetoken\n")
        return _make_proc()

    def test_subprocess_called_only_once_on_repeated_calls(self, monkeypatch):
        monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh" if name == "gh" else None)
        call_count = {"n": 0}

        def _counting_run(cmd, **kw):
            call_count["n"] += 1
            return self._auth_run(cmd, **kw)

        monkeypatch.setattr(subprocess, "run", _counting_run)
        monkeypatch.delenv("GH_TOKEN", raising=False)

        result1 = get_github_cli_prompt()
        result2 = get_github_cli_prompt()

        assert result1 == result2
        assert call_count["n"] == 2  # auth status + token on first call; zero on second
