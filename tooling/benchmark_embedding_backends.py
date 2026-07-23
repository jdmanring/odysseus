#!/usr/bin/env python3
"""Compare embedding backends on retrieval quality and per-item latency.

Reproduces the claims in docs/dev/memory-architecture.md's backend-selection
section: that retrieval accuracy is backend/quant-independent on this workload,
and that per-item latency (the hot path) is a few ms on llama.cpp Q8. Run it to
regenerate the numbers rather than trusting a stale figure in prose.

    venv/bin/python tooling/benchmark_embedding_backends.py

It builds a small topic-labelled corpus, embeds documents and queries with each
available backend (fastembed INT8 and llama.cpp Q8_0), and reports:
  * top-1 topic-match accuracy per backend (retrieval correctness), and
  * cross-backend ranking agreement (do they retrieve the same doc?), and
  * single-item embed latency (p50).

Only backends that are installed are run, so it works on the BSDs (llama.cpp
only) and elsewhere (both).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np

# Topic-labelled corpus: 4 topics x 3 documents, plus one query per topic whose
# correct answer is any document sharing its topic.
CORPUS = [
    ("astronomy", "A red giant is a dying star in a late phase of stellar evolution."),
    ("astronomy", "The event horizon marks the boundary of a black hole in spacetime."),
    ("astronomy", "Nebulae are clouds of interstellar gas where new stars are born."),
    ("cooking", "Searing meat at high heat develops flavour through the Maillard reaction."),
    ("cooking", "Proofing dough lets yeast ferment and the bread rise before baking."),
    ("cooking", "Emulsifying egg yolk and oil slowly is how you make mayonnaise."),
    ("finance", "A bond's yield moves inversely to its price on the secondary market."),
    ("finance", "Diversifying a portfolio spreads risk across uncorrelated assets."),
    ("finance", "Compound interest grows principal faster as returns are reinvested."),
    ("medicine", "Antibiotics treat bacterial infections but do nothing against viruses."),
    ("medicine", "The immune system produces antibodies in response to an antigen."),
    ("medicine", "Insulin regulates blood glucose by signalling cells to absorb sugar."),
]
QUERIES = [
    ("astronomy", "what happens to a star at the end of its life"),
    ("cooking", "why does browning make food taste better"),
    ("finance", "how does reinvesting returns build wealth over time"),
    ("medicine", "how does the body defend against an infection"),
]


def _rank(doc_vecs, query_vec):
    sims = doc_vecs @ query_vec
    return np.argsort(-sims)


def evaluate(client, name):
    labels = [t for t, _ in CORPUS]
    docs = [d for _, d in CORPUS]
    doc_vecs = np.asarray(client.encode(docs, is_query=False), dtype="float32")
    # single-item latency (the hot path): 20 reps of one short encode
    lat = []
    for _ in range(20):
        t = time.monotonic()
        client.encode([docs[0]], is_query=False)
        lat.append((time.monotonic() - t) * 1000)
    lat.sort()

    # bulk throughput: embed all docs in one batched call (the reindex path)
    bulk_docs = docs * 8  # 96 documents
    t = time.monotonic()
    client.encode(bulk_docs, is_query=False)
    bulk_s = time.monotonic() - t
    bulk_rate = len(bulk_docs) / bulk_s

    correct = 0
    top1_docs = []
    for topic, q in QUERIES:
        qv = np.asarray(client.encode([q], is_query=True), dtype="float32")[0]
        order = _rank(doc_vecs, qv)
        top1 = order[0]
        top1_docs.append(int(top1))
        if labels[top1] == topic:
            correct += 1
    acc = correct / len(QUERIES)
    print(f"  {name:16s} top-1 topic accuracy: {acc:.3f} "
          f"({correct}/{len(QUERIES)})   per-item p50: {lat[10]:.1f} ms   "
          f"bulk: {bulk_rate:.0f} docs/s")
    return acc, top1_docs


def main():
    print("Embedding backend comparison (retrieval accuracy + per-item latency)\n")
    results = {}
    # Force local backends (no HTTP endpoint) for a clean comparison.
    import os
    os.environ.pop("EMBEDDING_URL", None)
    from src.embeddings import LlamaCppEmbedClient
    try:
        from src.embeddings import FastEmbedClient
        fe = FastEmbedClient(); fe.get_sentence_embedding_dimension()
        results["fastembed"] = evaluate(fe, "fastembed INT8")
    except Exception as e:
        print(f"  fastembed: not available ({type(e).__name__}) — skipping")
    lc = LlamaCppEmbedClient(); lc.get_sentence_embedding_dimension()
    results["llamacpp"] = evaluate(lc, "llama.cpp Q8_0")

    if "fastembed" in results and "llamacpp" in results:
        fe_top1 = results["fastembed"][1]
        lc_top1 = results["llamacpp"][1]
        agree = sum(1 for a, b in zip(fe_top1, lc_top1) if a == b)
        print(f"\n  cross-backend top-1 agreement: {agree}/{len(QUERIES)} "
              f"queries retrieve the same document")
    print("\nInterpretation: equal accuracy across backends = retrieval is "
          "backend/quant-independent on this workload.")


if __name__ == "__main__":
    main()
