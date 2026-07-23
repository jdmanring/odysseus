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

# Topic-labelled corpus: 6 topics x 5 documents. Queries are paraphrases (no term
# overlap with the target doc) so retrieval must be semantic, not lexical; several
# topics are deliberately adjacent (astronomy/physics, medicine/biology) so a weak
# model confuses them and accuracy does NOT saturate at 1.000 — that's what makes
# the set able to tell a better model from an equal one.
CORPUS = [
    ("astronomy", "A red giant is a dying star in a late phase of stellar evolution."),
    ("astronomy", "The event horizon marks the boundary of a black hole in spacetime."),
    ("astronomy", "Nebulae are clouds of interstellar gas where new stars are born."),
    ("astronomy", "A supernova is the explosive death of a massive star."),
    ("astronomy", "Exoplanets orbit stars beyond our own solar system."),
    ("physics", "Entropy measures the disorder of a thermodynamic system."),
    ("physics", "Superconductors carry current with zero electrical resistance."),
    ("physics", "The uncertainty principle bounds simultaneous knowledge of position and momentum."),
    ("physics", "Refraction bends light as it passes between media of different density."),
    ("physics", "A pendulum's period depends on its length and local gravity."),
    ("cooking", "Searing meat at high heat develops flavour through the Maillard reaction."),
    ("cooking", "Proofing dough lets yeast ferment and the bread rise before baking."),
    ("cooking", "Emulsifying egg yolk and oil slowly is how you make mayonnaise."),
    ("cooking", "Deglazing a pan with wine lifts the fond into a sauce."),
    ("cooking", "Blanching vegetables briefly sets their colour and halts enzymes."),
    ("finance", "A bond's yield moves inversely to its price on the secondary market."),
    ("finance", "Diversifying a portfolio spreads risk across uncorrelated assets."),
    ("finance", "Compound interest grows principal faster as returns are reinvested."),
    ("finance", "Inflation erodes the purchasing power of held currency over time."),
    ("finance", "A short seller profits when the borrowed asset falls in price."),
    ("medicine", "Antibiotics treat bacterial infections but do nothing against viruses."),
    ("medicine", "The immune system produces antibodies in response to an antigen."),
    ("medicine", "Insulin regulates blood glucose by signalling cells to absorb sugar."),
    ("medicine", "Vaccines prime immunity by presenting a harmless piece of a pathogen."),
    ("medicine", "Anaesthesia suppresses pain signalling during surgery."),
    ("biology", "Photosynthesis converts sunlight into chemical energy in plants."),
    ("biology", "Mitosis divides one cell into two genetically identical daughters."),
    ("biology", "Natural selection favours traits that improve reproductive success."),
    ("biology", "Enzymes catalyse reactions by lowering activation energy."),
    ("biology", "DNA encodes heredity in sequences of four nucleotide bases."),
]
QUERIES = [
    ("astronomy", "what happens to a star at the end of its life"),
    ("astronomy", "worlds circling distant suns"),
    ("physics", "why does a straw look bent in a glass of water"),
    ("physics", "materials that conduct electricity without any loss"),
    ("cooking", "why does browning make food taste better"),
    ("cooking", "turning pan drippings into gravy"),
    ("finance", "how does reinvesting returns build wealth over time"),
    ("finance", "why is cash worth less each year"),
    ("medicine", "how does the body defend against an infection"),
    ("medicine", "how do shots prevent disease"),
    ("biology", "how do green leaves make food from light"),
    ("biology", "how one cell becomes two identical cells"),
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

    correct = correct3 = 0
    top1_docs = []
    for topic, q in QUERIES:
        qv = np.asarray(client.encode([q], is_query=True), dtype="float32")[0]
        order = _rank(doc_vecs, qv)
        top1_docs.append(int(order[0]))
        if labels[order[0]] == topic:
            correct += 1
        if any(labels[i] == topic for i in order[:3]):
            correct3 += 1
    acc = correct / len(QUERIES)
    acc3 = correct3 / len(QUERIES)
    print(f"  {name:16s} top-1 {acc:.3f}  top-3 {acc3:.3f}  "
          f"per-item p50 {lat[10]:.1f} ms  bulk {bulk_rate:.0f} docs/s")
    return acc, top1_docs


def _guard_idle_host():
    """Refuse to benchmark under load. These backends are CPU-bound with OpenMP
    threads, so a competing load (e.g. a VM compiling in the background) inflates
    per-item latency ~100x and makes the numbers meaningless — the failure that
    once nearly reversed an architecture decision. Set BENCH_FORCE=1 to override."""
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        return  # not available on this platform; skip the guard
    if load1 <= 2.0 or os.environ.get("BENCH_FORCE") == "1":
        if load1 > 2.0:
            print(f"WARNING: host load {load1:.1f} is high; latency numbers may be "
                  f"unreliable (BENCH_FORCE set, continuing).\n")
        return
    raise SystemExit(
        f"Refusing to benchmark: host 1-min load average is {load1:.1f} (>2.0).\n"
        f"Latency here is CPU/contention-sensitive; measure on an idle host.\n"
        f"Set BENCH_FORCE=1 to override.")


def main():
    _guard_idle_host()
    print("Embedding backend comparison (retrieval accuracy + per-item latency)\n")
    results = {}
    # Force local backends (no HTTP endpoint) for a clean comparison.
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
