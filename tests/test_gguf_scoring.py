"""Unit tests for HfUrlResolver GGUF quality scoring (no network required).

Tests _preferred_quant_file, _detect_imatrix, and _score_candidate — all
pure class/instance methods that operate on in-memory data with no HF API calls.
"""
from tooling.hf_url_resolver import HfUrlResolver


# ---------------------------------------------------------------------------
# _preferred_quant_file — quant priority ordering
# ---------------------------------------------------------------------------

def test_preferred_quant_picks_iq4_xs_over_q4_k_m():
    files = ["model.Q4_K_M.gguf", "model.IQ4_XS.gguf"]
    result = HfUrlResolver._preferred_quant_file(files)
    assert result == "model.IQ4_XS.gguf"


def test_preferred_quant_picks_q4_k_m_over_lower_quants():
    files = ["model.Q3_K_L.gguf", "model.Q4_K_M.gguf", "model.Q8_0.gguf"]
    result = HfUrlResolver._preferred_quant_file(files)
    assert result == "model.Q4_K_M.gguf"


def test_preferred_quant_picks_q5_k_m_over_q4_k_s():
    files = ["model.Q4_K_S.gguf", "model.Q5_K_M.gguf"]
    result = HfUrlResolver._preferred_quant_file(files)
    assert result == "model.Q5_K_M.gguf"


def test_preferred_quant_match_is_case_insensitive():
    files = ["model.q4_k_m.gguf"]
    result = HfUrlResolver._preferred_quant_file(files)
    assert result == "model.q4_k_m.gguf"


def test_preferred_quant_falls_back_to_first_when_no_match():
    files = ["model-fp32.gguf", "model-custom.gguf"]
    result = HfUrlResolver._preferred_quant_file(files)
    assert result == "model-fp32.gguf"


def test_preferred_quant_returns_none_for_empty_list():
    assert HfUrlResolver._preferred_quant_file([]) is None


# ---------------------------------------------------------------------------
# _detect_imatrix — repo name / author heuristic
# ---------------------------------------------------------------------------

def test_detect_imatrix_bartowski_author():
    assert HfUrlResolver._detect_imatrix("bartowski/Llama-3-8B-GGUF") is True


def test_detect_imatrix_duyntnet_author():
    assert HfUrlResolver._detect_imatrix("duyntnet/Qwen2-7B-Instruct-GGUF") is True


def test_detect_imatrix_repo_name_contains_imatrix():
    assert HfUrlResolver._detect_imatrix("unknown/Mistral-7B-imatrix-GGUF") is True


def test_detect_imatrix_repo_name_contains_imat():
    assert HfUrlResolver._detect_imatrix("someone/model-imat-v2-GGUF") is True


def test_detect_imatrix_false_for_plain_author_and_name():
    assert HfUrlResolver._detect_imatrix("TheBloke/Llama-2-7B-GGUF") is False


def test_detect_imatrix_false_for_unknown_author():
    assert HfUrlResolver._detect_imatrix("nobody/some-model-GGUF") is False


# ---------------------------------------------------------------------------
# _score_candidate — scoring invariants
# ---------------------------------------------------------------------------

def _base_candidate(**overrides):
    """Minimal candidate dict with no signals (score should be 0 without overrides)."""
    c = {
        "repo": "nobody/model-GGUF",
        "downloads": 0,
        "likes": 0,
        "likes_ratio": 0.0,
        "has_evals": False,
        "eval_score": None,
        "trending": None,
        "recency_days": None,
    }
    c.update(overrides)
    return c


def test_score_zero_signals_returns_zero():
    r = HfUrlResolver(token=None)
    assert r._score_candidate(_base_candidate()) == 0.0


def test_score_reputed_bartowski_gets_author_bonus():
    r = HfUrlResolver(token=None)
    score = r._score_candidate(_base_candidate(repo="bartowski/Llama-3-8B-GGUF"))
    # bartowski: +10 (reputed) + +15 (imatrix author)
    assert score >= 25.0


def test_score_imatrix_repo_name_gets_bonus():
    r = HfUrlResolver(token=None)
    with_imat = r._score_candidate(_base_candidate(repo="nobody/model-imatrix-GGUF"))
    without = r._score_candidate(_base_candidate())
    assert with_imat > without


def test_score_evals_increase_score():
    r = HfUrlResolver(token=None)
    base = _base_candidate(downloads=1000, likes=10, likes_ratio=0.01)
    with_evals = dict(base, has_evals=True, eval_score=75.0)
    assert r._score_candidate(with_evals) > r._score_candidate(base)


def test_score_recent_model_scores_higher_than_old():
    r = HfUrlResolver(token=None)
    old = _base_candidate(downloads=1000, likes=10, likes_ratio=0.01, recency_days=400)
    recent = dict(old, recency_days=10)
    assert r._score_candidate(recent) > r._score_candidate(old)


def test_score_downloads_increase_score():
    r = HfUrlResolver(token=None)
    no_dl = _base_candidate()
    with_dl = _base_candidate(downloads=50000, likes_ratio=0.0)
    assert r._score_candidate(with_dl) > r._score_candidate(no_dl)


def test_score_trending_increases_score():
    r = HfUrlResolver(token=None)
    no_trend = _base_candidate()
    trending = _base_candidate(trending=100.0)
    assert r._score_candidate(trending) > r._score_candidate(no_trend)


def test_score_downloads_capped_at_40():
    r = HfUrlResolver(token=None)
    # Massive downloads should saturate the downloads component at 40.
    huge_dl = _base_candidate(downloads=10_000_000)
    score = r._score_candidate(huge_dl)
    assert score <= 40.0 + 0.01  # only downloads signal active


# ── modern 6-bit variants (UD-Q6_K_XL / Q6_K_L) ─────────────────────────────

def test_preferred_quant_prefers_unsloth_dynamic_6bit_over_plain_q6k():
    files = ["model.Q6_K.gguf", "model.UD-Q6_K_XL.gguf", "model.Q4_K_M.gguf"]
    # No 4-bit imatrix present and UD-Q4 absent: the ladder reaches the 6-bit
    # entries via Q4_K_M first (size-conscious default) — so assert on a
    # 6-bit-only repo, the shape a Q6-floor user actually filters to.
    six_only = ["model.Q6_K.gguf", "model.UD-Q6_K_XL.gguf", "model.Q6_K_L.gguf"]
    result = HfUrlResolver._preferred_quant_file(six_only)
    assert result == "model.UD-Q6_K_XL.gguf"


def test_preferred_quant_prefers_q6kl_over_plain_q6k():
    files = ["model.Q6_K.gguf", "model.Q6_K_L.gguf"]
    result = HfUrlResolver._preferred_quant_file(files)
    assert result == "model.Q6_K_L.gguf"


def test_preferred_quant_prefers_ud_q4_over_iq4xs():
    files = ["model.IQ4_XS.gguf", "model.UD-Q4_K_XL.gguf"]
    result = HfUrlResolver._preferred_quant_file(files)
    assert result == "model.UD-Q4_K_XL.gguf"
