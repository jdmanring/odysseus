"""Pin isModelDownloaded (static/js/model/downloaded.js).

Driven through `node --input-type=module` (same approach as test_match_model_key_js.py);
skips when `node` is not installed.

Regression this locks: a catalog model downloaded from an auto-discovered quant repo
(catalog name != the GGUF repo the file actually came from) was reported downloaded by
some render sites and not by others, so installed models did not reliably grey out. The
fix is one canonical predicate; this is the test that fails if the gguf-aware match is
lost again.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_HELPER = _REPO / "static" / "js" / "model" / "downloaded.js"
_HAS_NODE = shutil.which("node") is not None


def _is_downloaded(model, cached):
    js = (
        f"import {{ isModelDownloaded }} from '{_HELPER.as_posix()}';"
        f"const cached = new Set({json.dumps(cached)});"
        f"console.log(JSON.stringify(isModelDownloaded({json.dumps(model)}, cached)));"
    )
    proc = subprocess.run(
        ["node", "--input-type=module"],
        input=js, capture_output=True, text=True, cwd=str(_REPO), timeout=30,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


pytestmark = pytest.mark.skipif(not _HAS_NODE, reason="node binary not on PATH")

_BETTER_QUANT_MODEL = {
    "name": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "gguf_sources": [{"repo": "bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"}],
}


def test_better_quant_repo_counts_as_downloaded():
    # THE lock: the file was pulled from the discovered quant repo, not the catalog
    # name. A name-only matcher (the old card-greying copy) returns False here; the
    # canonical predicate must return True.
    assert _is_downloaded(
        _BETTER_QUANT_MODEL, ["bartowski/Meta-Llama-3.1-8B-Instruct-GGUF"]) is True


def test_catalog_name_only_does_not_grey_without_gguf_match():
    # If neither the name nor any gguf repo is downloaded, it is not downloaded.
    assert _is_downloaded(_BETTER_QUANT_MODEL, ["someone/Unrelated-GGUF"]) is False


def test_full_name_match():
    assert _is_downloaded({"name": "org/Model-7B"}, ["org/Model-7B"]) is True


def test_short_name_fallback():
    # Cache stores the bare repo name; catalog carries the org-qualified id.
    assert _is_downloaded({"name": "org/Model-7B"}, ["Model-7B"]) is True
    # ... and the reverse (cache org-qualified, catalog bare) via endsWith.
    assert _is_downloaded({"name": "Model-7B"}, ["org/Model-7B"]) is True


def test_quant_repo_field_match():
    assert _is_downloaded(
        {"name": "org/Model", "quant_repo": "team/Model-AWQ"}, ["team/Model-AWQ"]) is True


def test_nothing_downloaded_is_false():
    assert _is_downloaded({"name": "org/Model"}, []) is False
    assert _is_downloaded({"name": "org/Model"}, ["other/Thing"]) is False


@pytest.mark.parametrize("catalog_name, downloaded", [
    # Real cases: a discovered catalog model (no gguf_sources) whose only link to
    # the downloaded community quant is the base name. These are the ones that did
    # not grey before.
    ("meta-llama/Llama-3.2-11B-Vision-Instruct", "leafspark/Llama-3.2-11B-Vision-Instruct-GGUF"),
    ("deepseek-ai/DeepSeek-V2-Lite-Chat", "legraphista/DeepSeek-V2-Lite-Chat-IMat-GGUF"),
    ("Qwen/Qwen3-30B-A3B", "nvidia/Qwen3-30B-A3B-NVFP4"),
    ("org/Qwen3-Coder-Next", "bullpoint/Qwen3-Coder-Next-AWQ-4bit"),
])
def test_base_model_match_for_discovered_quants(catalog_name, downloaded):
    # No gguf_sources on the catalog entry, so this must match by base name.
    assert _is_downloaded({"name": catalog_name}, [downloaded]) is True


def test_base_match_does_not_cross_distinct_models():
    # Different base (Instruct vs base, Coder vs base) must NOT match.
    assert _is_downloaded({"name": "org/Llama-3-8B"},
                          ["x/Llama-3-8B-Instruct-GGUF"]) is False
    assert _is_downloaded({"name": "org/Qwen3-8B"},
                          ["x/Qwen3-8B-Coder-AWQ"]) is False


def test_string_and_array_inputs():
    # The serve gate passes a bare string; the row re-mark passes an id list.
    assert _is_downloaded("org/Model-7B", ["org/Model-7B"]) is True
    assert _is_downloaded(
        ["org/Model-7B", "bartowski/Model-7B-GGUF"],
        ["bartowski/Model-7B-GGUF"]) is True
    assert _is_downloaded([], ["org/Model-7B"]) is False
