import os
import platform
from unittest.mock import patch

import pytest

from tooling.bin_manager import BinManager


# ---------------------------------------------------------------------------
# get_platform — no network, pure introspection
# ---------------------------------------------------------------------------

def test_get_platform_returns_two_strings():
    os_name, arch = BinManager.get_platform()
    assert isinstance(os_name, str) and os_name
    assert isinstance(arch, str) and arch


def test_get_platform_os_is_known_value():
    os_name, _ = BinManager.get_platform()
    assert os_name in {"Linux", "Darwin", "Windows"}


def test_get_platform_normalizes_amd64_to_x86_64():
    with patch("platform.machine", return_value="AMD64"), \
         patch("platform.system", return_value="Linux"):
        _, arch = BinManager.get_platform()
    assert arch == "x86_64"


def test_get_platform_preserves_arm64_on_darwin():
    with patch("platform.machine", return_value="arm64"), \
         patch("platform.system", return_value="Darwin"):
        os_name, arch = BinManager.get_platform()
    assert os_name == "Darwin" and arch == "arm64"


# ---------------------------------------------------------------------------
# TOOL_MAP structure — static contract, no network
# ---------------------------------------------------------------------------

def test_tool_map_has_aria2c():
    assert "aria2c" in BinManager.TOOL_MAP


def test_aria2c_has_linux_x86_64_entry():
    assert ("Linux", "x86_64") in BinManager.TOOL_MAP["aria2c"]


def test_aria2c_has_darwin_arm64_entry():
    assert ("Darwin", "arm64") in BinManager.TOOL_MAP["aria2c"]


def test_aria2c_entries_have_valid_structure():
    for platform_key, entry in BinManager.TOOL_MAP["aria2c"].items():
        url, archive_type, binary_name = entry
        assert url.startswith("https://"), f"Bad URL for {platform_key}"
        assert archive_type in {"zip", "tar.gz", "raw"}
        assert binary_name


# ---------------------------------------------------------------------------
# get_binary_path — checks disk only, no network
# ---------------------------------------------------------------------------

def test_get_binary_path_returns_none_when_absent(tmp_path):
    with patch.object(BinManager, "BIN_DIR", tmp_path):
        result = BinManager.get_binary_path("aria2c")
    assert result is None


def test_get_binary_path_returns_path_when_present(tmp_path):
    fake = tmp_path / "aria2c"
    fake.write_bytes(b"fake")
    fake.chmod(0o755)
    with patch.object(BinManager, "BIN_DIR", tmp_path):
        result = BinManager.get_binary_path("aria2c")
    assert result == fake


def test_get_binary_path_skips_non_executable(tmp_path):
    fake = tmp_path / "aria2c"
    fake.write_bytes(b"fake")
    fake.chmod(0o644)
    with patch.object(BinManager, "BIN_DIR", tmp_path):
        result = BinManager.get_binary_path("aria2c")
    assert result is None


# ---------------------------------------------------------------------------
# ensure_binary — unsupported inputs return None without touching the network
# ---------------------------------------------------------------------------

def test_ensure_binary_unknown_tool_returns_none():
    result = BinManager.ensure_binary("__no_such_tool__")
    assert result is None


def test_ensure_binary_unsupported_platform_returns_none():
    with patch.object(BinManager, "get_platform", return_value=("Solaris", "sparc")):
        result = BinManager.ensure_binary("aria2c")
    assert result is None
