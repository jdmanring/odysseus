"""GGUF discovery must never substitute an unrelated model (issue: a request
for tiny-random/qwen3-next-moe silently downloaded an unrelated 12B
"FreakStorm" merge that merely shared name tokens).

Tests _is_quant_of and the find_gguf_sources filter — no network; the HF API
is stubbed with recorded shapes from the real incident.
"""
from unittest.mock import MagicMock, patch

from tooling.hf_url_resolver import HfUrlResolver


def _resolver():
    return HfUrlResolver(token=None)


# ---------------------------------------------------------------------------
# _is_quant_of — the relatedness predicate
# ---------------------------------------------------------------------------

def test_base_models_metadata_match_accepts():
    r = _resolver()
    assert r._is_quant_of(
        "meta-llama/Llama-3.1-8B-Instruct",
        "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        ["meta-llama/Llama-3.1-8B-Instruct"],
    )


def test_base_models_match_is_case_insensitive():
    r = _resolver()
    assert r._is_quant_of(
        "meta-llama/Llama-3.1-8B-Instruct",
        "someone/whatever-GGUF",
        ["META-LLAMA/llama-3.1-8b-instruct"],
    )


def test_name_containment_fallback_accepts_true_quant_without_metadata():
    # bartowski-style repo name embeds the full base model name
    r = _resolver()
    assert r._is_quant_of(
        "meta-llama/Llama-3.1-8B-Instruct",
        "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF",
        [],
    )


def test_freakstorm_incident_is_rejected():
    # The recorded incident: name-token overlap ("Qwen3", "MOE", "Next") but
    # NOT a quantization of the requested model. Must be rejected on both
    # signals: base_models points elsewhere, and the full base name is not
    # contained in the candidate name.
    r = _resolver()
    assert not r._is_quant_of(
        "tiny-random/qwen3-next-moe",
        "mradermacher/Qwen3-MOE-2x6B-ST-The-Next-Generation-II-FreakStorm-12B-i1-GGUF",
        ["Disya/Qwen3-MOE-2x6B-ST-The-Next-Generation-II-FreakStorm-12B"],
    )


def test_partial_token_overlap_without_metadata_is_rejected():
    r = _resolver()
    assert not r._is_quant_of("org/Mistral-7B-Instruct-v0.3", "other/Mistral-Nemo-GGUF", [])


def test_wrong_base_models_metadata_alone_does_not_reject_when_name_contains():
    # A quant repo may list a fine-tune ancestor rather than the exact repo id;
    # the name-containment fallback still accepts it.
    r = _resolver()
    assert r._is_quant_of(
        "unsloth/Qwen3-8B",
        "someone/Qwen3-8B-abliterated-GGUF",
        ["some/other-ancestor"],
    )


def test_empty_base_name_never_matches():
    r = _resolver()
    assert not r._is_quant_of("org/---", "other/anything-GGUF", [])


# ---------------------------------------------------------------------------
# find_gguf_sources — filter is actually applied to search results
# ---------------------------------------------------------------------------

def _fake_model(repo_id):
    m = MagicMock()
    m.modelId = repo_id
    return m


def test_find_gguf_sources_drops_unrelated_and_keeps_derived():
    r = _resolver()
    probed = {
        "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF": {
            "files": ["a.Q4_K_M.gguf"], "downloads": 1000, "likes": 10,
            "likes_ratio": 0.01, "trending": None, "has_evals": False,
            "eval_score": None, "is_derived": True,
            "base_models": ["meta-llama/Llama-3.1-8B-Instruct"],
            "recency_days": 10, "imatrix": False, "author": "bartowski",
        },
        "mradermacher/Qwen3-MOE-FreakStorm-12B-i1-GGUF": {
            "files": ["b.Q6_K.gguf"], "downloads": 99999, "likes": 500,
            "likes_ratio": 0.005, "trending": 5, "has_evals": True,
            "eval_score": 50, "is_derived": True,
            "base_models": ["Disya/Qwen3-MOE-FreakStorm-12B"],
            "recency_days": 1, "imatrix": True, "author": "mradermacher",
        },
    }
    with patch.object(r, "api") as api, \
         patch.object(r, "_probe_gguf_repo", side_effect=lambda rid: dict(probed[rid])):
        api.list_models.return_value = [_fake_model(k) for k in probed]
        out = r.find_gguf_sources("meta-llama/Llama-3.1-8B-Instruct")
    repos = [s["repo"] for s in out]
    assert repos == ["bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"]


def test_find_gguf_sources_returns_empty_when_nothing_qualifies():
    # No substitute is ever better than an honest empty result.
    r = _resolver()
    unrelated = {
        "files": ["b.Q6_K.gguf"], "downloads": 99999, "likes": 500,
        "likes_ratio": 0.005, "trending": 5, "has_evals": True,
        "eval_score": 50, "is_derived": True,
        "base_models": ["Disya/Qwen3-MOE-FreakStorm-12B"],
        "recency_days": 1, "imatrix": True, "author": "mradermacher",
    }
    with patch.object(r, "api") as api, \
         patch.object(r, "_probe_gguf_repo", return_value=dict(unrelated)):
        api.list_models.return_value = [
            _fake_model("mradermacher/Qwen3-MOE-FreakStorm-12B-i1-GGUF")]
        out = r.find_gguf_sources("tiny-random/qwen3-next-moe")
    assert out == []
