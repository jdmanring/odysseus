"""Logo detection for Groq, Together.ai, and Fireworks AI provider entries.

All three providers already have backend detection (_detect_provider,
_provider_label, _PROVIDER_CURATED) but lacked entries in the _PROVIDERS
logo catalog in static/js/providers.js.  This file verifies:
  - providerLogo() matches known model-ID strings
  - providerLogoFromUrl() matches the real API endpoint hosts
  - providerLogoFromUrl() does NOT return the OpenAI logo for these endpoints
    (all three route through /openai/v1, which would match the OpenAI regex
     if these entries were not placed before OpenAI in _PROVIDERS)
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
    result = json.loads(p.stdout.strip())
    return result  # SVG string or null


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


# ── Groq ────────────────────────────────────────────────────────────────────

class TestGroqLogo:
    def test_model_id_gets_logo(self):
        assert _logo_for_model("groq/llama3-8b-8192") is not None

    def test_url_api_host_gets_logo(self):
        assert _logo_for_url("https://api.groq.com/openai/v1") is not None

    def test_url_does_not_return_openai_logo(self):
        groq_svg = _logo_for_url("https://api.groq.com/openai/v1")
        openai_svg = _openai_svg()
        assert groq_svg != openai_svg, "Groq endpoint returned OpenAI logo (ordering bug)"


# ── Together AI ──────────────────────────────────────────────────────────────

class TestTogetherLogo:
    def test_model_id_gets_logo(self):
        assert _logo_for_model("together/mistral-7b-instruct") is not None

    def test_url_xyz_host_gets_logo(self):
        assert _logo_for_url("https://api.together.xyz/v1") is not None

    def test_url_ai_host_gets_logo(self):
        assert _logo_for_url("https://api.together.ai/v1") is not None

    def test_url_does_not_return_openai_logo(self):
        together_svg = _logo_for_url("https://api.together.xyz/v1")
        assert together_svg != _openai_svg()


# ── Fireworks AI ─────────────────────────────────────────────────────────────

class TestFireworksLogo:
    def test_model_id_gets_logo(self):
        assert _logo_for_model("fireworks/accounts/fireworks/models/llama4-scout-instruct-basic") is not None

    def test_url_api_host_gets_logo(self):
        assert _logo_for_url("https://api.fireworks.ai/inference/v1") is not None

    def test_url_does_not_return_openai_logo(self):
        fw_svg = _logo_for_url("https://api.fireworks.ai/inference/v1")
        assert fw_svg != _openai_svg()
