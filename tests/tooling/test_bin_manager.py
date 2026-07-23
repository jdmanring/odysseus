import os
from unittest.mock import patch

import pytest

from tooling.bin_manager import BinManager


# ---------------------------------------------------------------------------
# get_platform — arch normalization
# ---------------------------------------------------------------------------

def test_get_platform_normalizes_amd64_to_x86_64_on_linux():
    # Linux reports "AMD64" on some distros; TOOL_MAP key is "x86_64".
    with patch("platform.machine", return_value="AMD64"), \
         patch("platform.system", return_value="Linux"):
        _, arch = BinManager.get_platform()
    assert arch == "x86_64"


def test_get_platform_preserves_amd64_on_windows():
    # Windows keeps "AMD64" — TOOL_MAP key is ("Windows", "AMD64"), not "x86_64".
    # Normalizing it would silently miss the TOOL_MAP entry and skip the download.
    with patch("platform.machine", return_value="AMD64"), \
         patch("platform.system", return_value="Windows"):
        _, arch = BinManager.get_platform()
    assert arch == "AMD64"


def test_get_platform_preserves_arm64_on_darwin():
    # macOS Apple Silicon stays "arm64"; Linux ARM stays "aarch64".
    # Conflating the two would map to the wrong static build.
    with patch("platform.machine", return_value="arm64"), \
         patch("platform.system", return_value="Darwin"):
        os_name, arch = BinManager.get_platform()
    assert os_name == "Darwin" and arch == "arm64"


# ---------------------------------------------------------------------------
# TOOL_MAP structure — static contract, no network
# ---------------------------------------------------------------------------

def test_aria2c_has_linux_x86_64_entry():
    assert ("Linux", "x86_64") in BinManager.TOOL_MAP["aria2c"]


def test_aria2c_darwin_uses_which_fallback_not_a_bundled_binary():
    # No maintained static aria2c build exists for Darwin, and a GitHub binary
    # would be Gatekeeper-quarantined; macOS installs aria2c at setup time
    # (brew/conda) and get_aria2c() resolves it via shutil.which. So BinManager
    # deliberately has NO Darwin entry, forcing that resolution path.
    assert ("Darwin", "arm64") not in BinManager.TOOL_MAP["aria2c"]
    assert ("Darwin", "x86_64") not in BinManager.TOOL_MAP["aria2c"]
    from pathlib import Path as _P
    src = (_P(__file__).resolve().parents[2] / "tooling/aria2c_download.py").read_text()
    assert 'shutil.which("aria2c")' in src


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
    # get_binary_path looks for the platform's binary name (aria2c.exe on
    # Windows) — plant the right one so this passes on native-Windows runs.
    fake = tmp_path / ("aria2c.exe" if os.name == "nt" else "aria2c")
    fake.write_bytes(b"fake")
    fake.chmod(0o755)
    with patch.object(BinManager, "BIN_DIR", tmp_path):
        result = BinManager.get_binary_path("aria2c")
    assert result == fake


@pytest.mark.skipif(os.name == "nt", reason="chmod bits carry no executable semantics on Windows")
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
