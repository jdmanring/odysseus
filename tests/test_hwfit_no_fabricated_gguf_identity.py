"""Issue #149: HW-Fit must not fabricate a GGUF identity for plain safetensors
models. A BF16 research repo with no GGUF anywhere was rated at a hypothetical
Q4_K_M, so the UI showed "Q4_K_M / llama.cpp", Run picked the wrong engine, and
Download hunted a GGUF that does not exist (screenshot:
docs/fork/screenshots/dspark.png)."""
from services.hwfit.fit import analyze_model


def _single_gpu_cuda_system():
    return {
        "has_gpu": True,
        "backend": "cuda",
        "gpu_name": "NVIDIA GeForce RTX 4070 Ti SUPER",
        "gpu_vram_gb": 21.9,
        "gpu_count": 1,
        "available_ram_gb": 30.5,
        "total_ram_gb": 30.5,
    }


def _dspark_like():
    # Mirrors the recorded incident entry (data/hwfit/hf_collection_models.json)
    return {
        "name": "deepseek-ai/dspark_qwen3_4b_block7",
        "provider": "deepseek-ai",
        "parameter_count": "1.393B",
        "parameters_raw": 1393133569,
        "quantization": "BF16",
        "context_length": 32768,
        "format": "safetensors",
    }


def test_safetensors_model_without_gguf_is_rated_at_native_precision():
    row = analyze_model(_dspark_like(), _single_gpu_cuda_system())
    assert row is not None
    assert row["quant"] == "BF16", "no GGUF evidence → native precision, never a fabricated Q tier"
    assert row["format"] == "safetensors"
    assert row["is_gguf"] is False


def test_catalog_legacy_q4km_default_is_guarded_for_safetensors():
    m = _dspark_like()
    del m["quantization"]  # legacy entries default to Q4_K_M in _native_quant
    row = analyze_model(m, _single_gpu_cuda_system())
    assert row is not None
    assert not row["quant"].upper().startswith(("Q", "IQ")), \
        "quantization-less safetensors entry must not inherit the Q4_K_M default"


def test_model_with_real_gguf_sources_keeps_q4km_default():
    m = _dspark_like()
    m["gguf_sources"] = [{"repo": "bartowski/whatever-GGUF"}]
    row = analyze_model(m, _single_gpu_cuda_system())
    assert row is not None
    assert row["quant"] == "Q4_K_M", "real GGUF path keeps the preferred llama.cpp default"


def test_rows_expose_format_and_gguf_evidence_for_client_detection():
    row = analyze_model(_dspark_like(), _single_gpu_cuda_system())
    assert "format" in row and "is_gguf" in row, \
        "client backend detection needs real evidence fields, not just the quant label"
