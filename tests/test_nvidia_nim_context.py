"""Tests for NVIDIA NIM context window coverage and curated model list.

Covers the two gaps fixed in feat/nvidia-nim-support:
  1. KNOWN_CONTEXT_WINDOWS now covers all 30 previously-unrecognised NIM models
     and corrects stale values for 6 models.
  2. _PROVIDER_CURATED gains an "nvidia" entry so the NIM model list is ordered
     with flagship models first instead of raw alphabetical.
"""
import sys
import types

import pytest

from src.model_context import _lookup_known


# ---------------------------------------------------------------------------
# Previously unrecognised NIM models — must now return the correct window
# ---------------------------------------------------------------------------

class TestNimUnrecognisedModelsNowCovered:
    """All 30 models that previously fell through to (DEFAULT_CONTEXT, False)."""

    def test_deepseek_v4_pro(self):
        assert _lookup_known("deepseek-ai/deepseek-v4-pro") == 1_000_000

    def test_deepseek_v4_flash(self):
        assert _lookup_known("deepseek-ai/deepseek-v4-flash") == 1_000_000

    def test_glm_5_1(self):
        assert _lookup_known("z-ai/glm-5.1") == 131_072

    def test_seed_oss_36b(self):
        assert _lookup_known("bytedance/seed-oss-36b-instruct") == 512_000

    def test_step_3_5_flash(self):
        assert _lookup_known("stepfun-ai/step-3.5-flash") == 262_144

    def test_step_3_7_flash(self):
        assert _lookup_known("stepfun-ai/step-3.7-flash") == 262_144

    def test_gpt_oss_120b(self):
        assert _lookup_known("openai/gpt-oss-120b") == 131_072

    def test_gpt_oss_20b(self):
        assert _lookup_known("openai/gpt-oss-20b") == 131_072

    def test_granite_3_0_8b(self):
        assert _lookup_known("ibm/granite-3.0-8b-instruct") == 4_096

    def test_granite_3_0_3b(self):
        assert _lookup_known("ibm/granite-3.0-3b-a800m-instruct") == 4_096

    def test_granite_34b_code(self):
        assert _lookup_known("ibm/granite-34b-code-instruct") == 8_192

    def test_granite_8b_code(self):
        # NIM serves the base 8K model (not the -128k variant)
        assert _lookup_known("ibm/granite-8b-code-instruct") == 8_192

    def test_codellama_70b(self):
        assert _lookup_known("meta/codellama-70b") == 16_384

    def test_llama2_70b(self):
        assert _lookup_known("meta/llama2-70b") == 4_096

    def test_ministral_14b(self):
        assert _lookup_known("mistralai/ministral-14b-instruct-2512") == 262_144

    def test_sarvam_m(self):
        # NIM ISL limit (8K), not the model's architectural window (32K)
        assert _lookup_known("sarvamai/sarvam-m") == 8_192

    def test_starcoder2_15b(self):
        assert _lookup_known("bigcode/starcoder2-15b") == 8_192

    def test_dbrx_instruct(self):
        assert _lookup_known("databricks/dbrx-instruct") == 32_768

    def test_jamba_1_5_large(self):
        assert _lookup_known("ai21labs/jamba-1.5-large-instruct") == 256_000

    def test_zamba2_7b(self):
        assert _lookup_known("zyphra/zamba2-7b-instruct") == 16_384

    def test_chatqa_1_5_70b(self):
        assert _lookup_known("nvidia/llama3-chatqa-1.5-70b") == 8_192

    def test_sea_lion_7b(self):
        assert _lookup_known("aisingapore/sea-lion-7b-instruct") == 4_096

    def test_stockmark_100b(self):
        assert _lookup_known("stockmark/stockmark-2-100b-instruct") == 128_000

    def test_palmyra_creative(self):
        assert _lookup_known("writer/palmyra-creative-122b") == 131_072

    def test_palmyra_fin(self):
        assert _lookup_known("writer/palmyra-fin-70b-32k") == 32_768

    def test_palmyra_med(self):
        assert _lookup_known("writer/palmyra-med-70b") == 32_768

    def test_palmyra_med_32k(self):
        assert _lookup_known("writer/palmyra-med-70b-32k") == 32_768

    def test_embed_qa_4(self):
        assert _lookup_known("nvidia/embed-qa-4") == 512

    def test_codegemma_1_1(self):
        assert _lookup_known("google/codegemma-1.1-7b") == 8_192

    def test_codegemma_7b(self):
        assert _lookup_known("google/codegemma-7b") == 8_192


# ---------------------------------------------------------------------------
# Stale-value corrections — recognised models that had wrong windows
# ---------------------------------------------------------------------------

class TestStaleValueCorrections:
    """Models already in the table whose values were wrong for the NIM deployment."""

    def test_kimi_k2_6_beats_kimi_and_moonshot(self):
        # kimi-k2.6 on NIM: ISL 262,144. The old 'kimi'/'moonshot' keys returned 128K.
        # 'kimi-k2' (len=7) beats 'kimi' (len=4) and 'moonshot' (len=8) ... wait,
        # 'moonshot' is len 8 and 'kimi-k2' is len 7. The model name is
        # "moonshotai/kimi-k2.6". basename after split("/") is "kimi-k2.6".
        # 'moonshot' is NOT in "kimi-k2.6"; 'kimi-k2' IS in "kimi-k2.6".
        assert _lookup_known("moonshotai/kimi-k2.6") == 262_144

    def test_kimi_non_k2_still_returns_128k(self):
        # kimi-1.5 or a plain kimi model should still get 128K via the 'kimi' key
        assert _lookup_known("moonshotai/kimi-1.5") == 128_000

    def test_mistral_small_4_beats_mistral_small(self):
        assert _lookup_known("mistralai/mistral-small-4-119b-2603") == 262_144

    def test_mistral_small_non_4_still_32k(self):
        # Non-v4 mistral-small variants should still get 32K
        assert _lookup_known("mistralai/mistral-small-latest") == 32_000

    def test_mistral_medium_3_5_beats_mistral_medium(self):
        assert _lookup_known("mistralai/mistral-medium-3.5-128b") == 262_144

    def test_mixtral_8x22b_beats_mixtral(self):
        assert _lookup_known("mistralai/mixtral-8x22b-v0.1") == 65_536

    def test_mixtral_8x7b_still_32k(self):
        assert _lookup_known("mistralai/mixtral-8x7b-instruct-v0.1") == 32_000

    def test_deepseek_coder_corrected_to_4k(self):
        # deepseek-coder-6.7b on NIM has 4K context; old value was 64K.
        assert _lookup_known("deepseek-ai/deepseek-coder-6.7b-instruct") == 4_096

    def test_deepseek_v3_updated_to_128k(self):
        assert _lookup_known("deepseek-ai/deepseek-v3") == 128_000

    def test_deepseek_r1_updated_to_128k(self):
        assert _lookup_known("deepseek-ai/deepseek-r1") == 128_000

    def test_minitron_8k_beats_mistral_nemo(self):
        # mistral-nemo key returns 128K; the more specific key must win.
        assert _lookup_known("nvidia/mistral-nemo-minitron-8b-8k-instruct") == 8_192

    def test_mistral_nemo_non_minitron_still_128k(self):
        assert _lookup_known("mistralai/mistral-nemo-instruct-2407") == 128_000


# ---------------------------------------------------------------------------
# Longest-key invariant — new keys must not shadow shorter, broader keys
# ---------------------------------------------------------------------------

class TestLongestKeyInvariant:
    """Sanity-check that more specific new keys don't over-match related models."""

    def test_granite_3_1_matches_granite_3_not_granite_3_0(self):
        # granite-3.1-8b-instruct should NOT get granite-3.0's 4K value
        result = _lookup_known("ibm/granite-3.1-8b-instruct")
        assert result == 128_000  # 'granite-3' key

    def test_granite_3_2_matches_granite_3(self):
        result = _lookup_known("ibm/granite-3.2-8b-instruct")
        assert result == 128_000

    def test_palmyra_creative_longer_key_wins(self):
        # palmyra-creative-122b should get 131072, not palmyra's 32768
        assert _lookup_known("writer/palmyra-creative-122b") == 131_072

    def test_gpt_oss_does_not_shadow_gpt_4o(self):
        # 'gpt-oss' must not accidentally match 'gpt-4o-mini' etc.
        assert _lookup_known("gpt-4o") == 128_000
        assert _lookup_known("gpt-4o-mini") == 128_000

    def test_step_3_does_not_shadow_gpt_3_5(self):
        # 'step-3' contains "3" but NOT "step-3" — check it doesn't match gpt-3.5
        result = _lookup_known("gpt-3.5-turbo")
        assert result == 16_385  # 'gpt-3.5-turbo' key, not 'step-3'

    def test_deepseek_v4_does_not_override_v3(self):
        assert _lookup_known("deepseek-ai/deepseek-v3") == 128_000
        assert _lookup_known("deepseek-ai/deepseek-v4-pro") == 1_000_000


# ---------------------------------------------------------------------------
# Curated list — nvidia key added to _PROVIDER_CURATED
# ---------------------------------------------------------------------------

def _build_curated_key_from_url():
    """Return the curated key that _match_provider_curated would return for NIM."""
    # Import here to isolate from the table tests above
    from routes.model_routes import _match_provider_curated
    return _match_provider_curated("https://integrate.api.nvidia.com/v1", "openai")


class TestNvidiaCuratedList:
    def test_nvidia_key_exists_in_provider_curated(self):
        from routes.model_routes import _PROVIDER_CURATED
        assert "nvidia" in _PROVIDER_CURATED

    def test_nvidia_curated_list_is_nonempty(self):
        from routes.model_routes import _PROVIDER_CURATED
        assert len(_PROVIDER_CURATED["nvidia"]) > 0

    def test_deepseek_v4_pro_in_nvidia_curated(self):
        from routes.model_routes import _PROVIDER_CURATED
        curated = _PROVIDER_CURATED["nvidia"]
        assert any("deepseek-v4-pro" in entry for entry in curated)

    def test_nemotron_in_nvidia_curated(self):
        from routes.model_routes import _PROVIDER_CURATED
        curated = _PROVIDER_CURATED["nvidia"]
        assert any("nemotron" in entry for entry in curated)

    def test_nvidia_host_resolves_to_nvidia_key(self):
        key = _build_curated_key_from_url()
        assert key == "nvidia"

    def test_curate_models_partitions_nim_models(self, monkeypatch):
        """NIM model IDs are split into curated + extra; curated appears first."""
        from routes.model_routes import _curate_models, _PROVIDER_CURATED
        curated_entries = _PROVIDER_CURATED["nvidia"]
        # Build a synthetic model list: one curated, one not
        primary = curated_entries[0]
        extra = "01-ai/yi-large"  # alphabetically first but not in curated list
        model_ids = [extra, primary]
        curated_out, extra_out = _curate_models(model_ids, "nvidia")
        assert primary in curated_out
        assert extra in extra_out
        assert extra not in curated_out
