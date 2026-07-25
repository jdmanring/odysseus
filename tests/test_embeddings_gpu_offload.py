"""GPU-offload knobs for the llama.cpp embedder: default-off, env-driven,
vendor-neutral (n_gpu_layers is honored by every llama.cpp GPU backend and
ignored by CPU-only builds). Measured motivation lives in
docs/dev/memory-architecture.md; these tests pin the config plumbing."""
import sys
import types

import pytest


class _FakeLlama:
    captured = {}

    @classmethod
    def from_pretrained(cls, **kwargs):
        cls.captured = kwargs
        return cls()

    def embed(self, *a, **k):
        return [[0.0] * 768]


@pytest.fixture
def fake_llama_cpp(monkeypatch):
    mod = types.ModuleType("llama_cpp")
    mod.Llama = _FakeLlama
    mod.LLAMA_POOLING_TYPE_MEAN = 1
    mod.LLAMA_ROPE_SCALING_TYPE_YARN = 2
    monkeypatch.setitem(sys.modules, "llama_cpp", mod)
    _FakeLlama.captured = {}
    return mod


def test_gpu_layers_default_zero(fake_llama_cpp, monkeypatch):
    monkeypatch.delenv("ODYSSEUS_EMBED_GPU_LAYERS", raising=False)
    monkeypatch.delenv("ODYSSEUS_EMBED_GPU_DEVICE", raising=False)
    from src.embeddings import LlamaCppEmbedClient
    LlamaCppEmbedClient()
    assert _FakeLlama.captured["n_gpu_layers"] == 0


def test_gpu_layers_env_passthrough(fake_llama_cpp, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_EMBED_GPU_LAYERS", "99")
    monkeypatch.delenv("ODYSSEUS_EMBED_GPU_DEVICE", raising=False)
    monkeypatch.delenv("GGML_VK_VISIBLE_DEVICES", raising=False)
    from src.embeddings import LlamaCppEmbedClient
    LlamaCppEmbedClient()
    assert _FakeLlama.captured["n_gpu_layers"] == 99
    # no device requested: the Vulkan device-mask env must stay untouched
    import os
    assert "GGML_VK_VISIBLE_DEVICES" not in os.environ


def test_gpu_device_sets_vulkan_mask_before_context(fake_llama_cpp, monkeypatch):
    monkeypatch.setenv("ODYSSEUS_EMBED_GPU_LAYERS", "99")
    monkeypatch.setenv("ODYSSEUS_EMBED_GPU_DEVICE", "1")
    monkeypatch.delenv("GGML_VK_VISIBLE_DEVICES", raising=False)
    from src.embeddings import LlamaCppEmbedClient
    LlamaCppEmbedClient()
    import os
    assert os.environ["GGML_VK_VISIBLE_DEVICES"] == "1"


def test_device_without_layers_is_inert(fake_llama_cpp, monkeypatch):
    # A device index with offload disabled must not touch process env:
    # the knob combination is meaningless and should change nothing.
    monkeypatch.delenv("ODYSSEUS_EMBED_GPU_LAYERS", raising=False)
    monkeypatch.setenv("ODYSSEUS_EMBED_GPU_DEVICE", "1")
    monkeypatch.delenv("GGML_VK_VISIBLE_DEVICES", raising=False)
    from src.embeddings import LlamaCppEmbedClient
    LlamaCppEmbedClient()
    import os
    assert "GGML_VK_VISIBLE_DEVICES" not in os.environ
    assert _FakeLlama.captured["n_gpu_layers"] == 0
