#!/usr/bin/env python3
"""Moved: the embedding-model evaluation matrix grew into Biscuit.

The model matrix that started here (candidate models on memory-shaped
retrieval, long-context fact recall, multilingual sets) outgrew a single
script and now lives as a standalone benchmark repository with its own
corpus, statistics, and paper:

    https://github.com/jdmanring/biscuit-bench   (private until release)

Odysseus-specific benchmarks remain in this directory:

    benchmark_embedding_backends.py  - fastembed vs llama.cpp on the app's model
    benchmark_memory_store.py        - vector-store latency on the app's stack

Findings that drove Odysseus decisions are summarized where they apply:
docs/dev/memory-architecture.md (backend choice, GPU offload, thread caps).
"""
import sys

if __name__ == "__main__":
    print(__doc__.strip(), file=sys.stderr)
    raise SystemExit(1)
