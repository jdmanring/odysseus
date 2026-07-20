"""Static wiring guards for the HW-Fit list UI (sort + quant filter).

Two live-reported defects:
- Sorting by Score refetched and re-rendered the whole ~2500-row scan twice
  (localStorage parse + server round-trip) — a "tremendous lag" for what is a
  pure in-memory table operation.
- The quant filter was enforced server-side only; client-synthesized Ollama
  rows (all Q4_K_M) were concatenated after filtering, so "only Q6" still
  mixed in Q4_K_M Ollama rows.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HWFIT_JS = (REPO / "static" / "js" / "cookbook-hwfit.js").read_text(encoding="utf-8")


def test_sort_click_resorts_in_memory_never_refetching_first():
    assert "function _hwfitResort()" in HWFIT_JS
    assert "if (!_hwfitResort()) _hwfitFetch();" in HWFIT_JS, \
        "column-sort click must re-sort the in-memory scan; fetch only as fallback"


def test_sort_logic_is_shared_between_fetch_and_resort():
    assert HWFIT_JS.count("_sortHwfitModels(") >= 3, \
        "one sort implementation, used by both the fetch pipeline and the resort path"


def test_ollama_rows_respect_the_quant_filter():
    merge = HWFIT_JS.split("_ollamaToHwfitRows(_lib", 1)[1][:2000]
    assert "quantPref" in merge, \
        "client-merged Ollama rows must pass the same quant filter as server rows"
    assert "=== _qp" in merge
