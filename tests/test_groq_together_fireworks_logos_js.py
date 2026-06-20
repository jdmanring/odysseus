"""Logo detection for Groq, Together.ai, Fireworks AI, and Pollinations AI.

These providers were added to _PROVIDERS in static/js/providers.js and must
appear BEFORE the OpenAI entry — all four route through URL paths that contain
the word "openai" (e.g. /openai/v1, /openai), which would match the OpenAI
regex (/openai|gpt-/i) if the ordering is wrong.

Google Gemini is also tested here because its OpenAI-compatible endpoint
(https://generativelanguage.googleapis.com/v1beta/openai) contains "openai"
in the path, causing the same ordering regression if Google is placed after
OpenAI in the _PROVIDERS array.

Checks:
  - providerLogo() matches known model-ID strings
  - providerLogoFromUrl() matches the real API endpoint hosts
  - providerLogoFromUrl() does NOT return the OpenAI logo for these endpoints
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

    def test_svg_has_evenodd_fill_rule(self):
        svg = _logo_for_model("together/mistral-7b-instruct")
        assert svg is not None and "evenodd" in svg, (
            "Together AI logo must use evenodd fill-rule for Venn diagram slots"
        )


# ── Fireworks AI ─────────────────────────────────────────────────────────────

class TestFireworksLogo:
    def test_model_id_gets_logo(self):
        assert _logo_for_model("fireworks/accounts/fireworks/models/llama4-scout-instruct-basic") is not None

    def test_url_api_host_gets_logo(self):
        assert _logo_for_url("https://api.fireworks.ai/inference/v1") is not None

    def test_url_does_not_return_openai_logo(self):
        fw_svg = _logo_for_url("https://api.fireworks.ai/inference/v1")
        assert fw_svg != _openai_svg()


# ── Pollinations AI ───────────────────────────────────────────────────────────
# text.pollinations.ai/openai — path contains "openai", so ordering vs OpenAI matters

class TestPollinationsLogo:
    _POLLINATIONS_URL = "https://text.pollinations.ai/openai"

    def test_model_id_gets_logo(self):
        assert _logo_for_model("pollinations/openai-large") is not None

    def test_url_host_gets_logo(self):
        assert _logo_for_url(self._POLLINATIONS_URL) is not None

    def test_url_does_not_return_openai_logo(self):
        poll_svg = _logo_for_url(self._POLLINATIONS_URL)
        assert poll_svg != _openai_svg(), (
            "Pollinations endpoint returned OpenAI logo — "
            "Pollinations entry must precede OpenAI in _PROVIDERS"
        )


# ── Google Gemini ─────────────────────────────────────────────────────────────
# The Google OpenAI-compat URL has /v1beta/openai in the path, which triggers
# the OpenAI regex if Google is not placed before OpenAI in _PROVIDERS.

class TestGoogleGeminiLogo:
    _GOOGLE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"

    def test_model_id_gets_logo(self):
        assert _logo_for_model("gemini-2.0-flash") is not None

    def test_url_googleapis_host_gets_logo(self):
        assert _logo_for_url(self._GOOGLE_URL) is not None

    def test_url_does_not_return_openai_logo(self):
        google_svg = _logo_for_url(self._GOOGLE_URL)
        assert google_svg != _openai_svg(), (
            "Google Gemini endpoint returned OpenAI logo — "
            "Google entry must precede OpenAI in _PROVIDERS"
        )
