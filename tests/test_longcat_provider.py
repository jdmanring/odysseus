"""LongCat (Meituan) provider integration tests.

Verifies that the longcat.chat API endpoint is correctly classified by the
provider-detection stack, the friendly label is returned instead of the raw
hostname, the curated model list is reachable, and the 1M-token context window
is reported for LongCat-2.0-Preview.

Sources:
  - API reference: https://longcat.chat/platform/docs/APIDocs.html
  - Model context: 1,048,576 tokens (reported in the LongCat platform docs)
"""

import pytest

from src import llm_core
from routes.model_routes import _match_provider_curated, _PROVIDER_CURATED
from src.model_context import _lookup_known


# ── Provider detection ──────────────────────────────────────────────────────

class TestLongCatDetect:
    def test_api_host_detected(self):
        assert llm_core._detect_provider("https://api.longcat.chat/openai/v1") == "longcat"

    def test_bare_apex_detected(self):
        assert llm_core._detect_provider("https://longcat.chat/openai/v1") == "longcat"

    def test_lookalike_not_detected(self):
        assert llm_core._detect_provider("https://longcat.chat.evil.com/openai/v1") != "longcat"

    def test_domain_in_path_not_detected(self):
        assert llm_core._detect_provider("https://myproxy.internal/longcat.chat/v1") != "longcat"


# ── Friendly label ──────────────────────────────────────────────────────────

class TestLongCatLabel:
    def test_api_host_label(self):
        assert llm_core._provider_label("https://api.longcat.chat/openai/v1") == "LongCat"

    def test_bare_apex_label(self):
        assert llm_core._provider_label("https://longcat.chat/openai/v1") == "LongCat"


# ── Curated model list ──────────────────────────────────────────────────────

class TestLongCatCurated:
    def test_url_matches_curated_key(self):
        assert _match_provider_curated("https://api.longcat.chat/openai/v1", "openai") == "longcat"

    def test_curated_list_has_preview_model(self):
        assert "LongCat-2.0-Preview" in _PROVIDER_CURATED["longcat"]

    def test_curated_list_is_nonempty(self):
        assert len(_PROVIDER_CURATED["longcat"]) >= 1


# ── Context window ──────────────────────────────────────────────────────────

class TestLongCatContextWindow:
    def test_preview_model_context(self):
        """LongCat-2.0-Preview has a 1M-token context window (1,048,576 tokens).
        Source: https://longcat.chat/platform/docs/APIDocs.html
        """
        assert _lookup_known("LongCat-2.0-Preview") == 1048576

    def test_namespaced_model_context(self):
        """Provider-prefixed form should still resolve."""
        assert _lookup_known("longcat/LongCat-2.0-Preview") == 1048576
