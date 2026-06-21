"""Logo and label detection for Pollinations AI provider entry.

Pollinations serves an OpenAI-compatible API at
https://text.pollinations.ai/openai — the path /openai matches the OpenAI
regex unless Pollinations is placed before OpenAI in _PROVIDERS.  This file
verifies that the ordering is correct and that the endpoint label is mapped.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HELPER = _REPO / "static" / "js" / "providers.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not on PATH")


def _logo_for_model(model_id: str) -> str | None:
    js = (
        f"import {{ providerLogo }} from '{_HELPER.as_posix()}';"
        f"console.log(JSON.stringify(providerLogo({json.dumps(model_id)})));"
    )
    p = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, cwd=str(_REPO), timeout=30,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip())


def _logo_for_url(url: str) -> str | None:
    js = (
        f"import {{ providerLogoFromUrl }} from '{_HELPER.as_posix()}';"
        f"console.log(JSON.stringify(providerLogoFromUrl({json.dumps(url)})));"
    )
    p = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, cwd=str(_REPO), timeout=30,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip())


def _label_for_url(url: str) -> str | None:
    js = (
        f"import {{ providerLabel }} from '{_HELPER.as_posix()}';"
        f"console.log(JSON.stringify(providerLabel({json.dumps(url)})));"
    )
    p = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, cwd=str(_REPO), timeout=30,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip())


def _openai_svg() -> str:
    js = (
        f"import {{ providerLogo }} from '{_HELPER.as_posix()}';"
        f"console.log(JSON.stringify(providerLogo('gpt-4o')));"
    )
    p = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, cwd=str(_REPO), timeout=30,
    )
    assert p.returncode == 0, p.stderr
    return json.loads(p.stdout.strip())


# ── Pollinations AI ──────────────────────────────────────────────────────────

class TestPollinationsLogo:
    def test_model_id_gets_logo(self):
        assert _logo_for_model("pollinations/openai-fast") is not None

    def test_url_text_host_gets_logo(self):
        assert _logo_for_url("https://text.pollinations.ai/openai") is not None

    def test_url_does_not_return_openai_logo(self):
        logo = _logo_for_url("https://text.pollinations.ai/openai")
        assert logo != _openai_svg(), "Pollinations endpoint returned OpenAI logo (ordering bug)"

    def test_label_pollinations_host(self):
        assert _label_for_url("https://text.pollinations.ai/openai") == "Pollinations"
