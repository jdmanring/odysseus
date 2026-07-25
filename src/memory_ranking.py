"""Shared BM25 scoring and dense+lexical fusion for memory recall.

One implementation for every recall path (chat context injection, the
agent's recall tool, the MCP memory server, the memory API). Before this
module, the chat path hand-rolled a binary-tf BM25 while the other paths
used a keyword-category heuristic — the same query could rank the same
memories three different ways.

The fusion shape (dense similarity + BM25 + small recency tiebreaker) is
the deployed chat-path scheme; the benchmark's dense+BM25 study found the
lexical term directionally lifts exactly the stale/temporal cases dense
similarity underweights ("switched", "as of", "now"), unproven at
benchmark scale (4-1 discordant, p=0.375) but deployable at zero
infrastructure cost. Weights are per-call so the chat path keeps its
live-tested values.

Superseded entries (see memory_supersede) are filtered here, so no fused
path can resurface a fact that has been replaced.
"""

import math
import time
from typing import Dict, List, Optional, Sequence, Tuple

from src.memory_supersede import is_superseded

# Okapi BM25 parameters (standard defaults; same values the benchmark used).
K1 = 1.5
B = 0.75


def _tokens(text: str) -> List[str]:
    return [t for t in "".join(
        c.lower() if c.isalnum() else " " for c in text
    ).split() if len(t) > 1]


def bm25_scores(query: str, entries: Sequence[Dict]) -> Dict[str, float]:
    """Okapi BM25 of query against entry texts, normalized to 0-1 by the
    best-scoring entry (per-query max normalization: fusion weights then
    mean the same thing regardless of corpus statistics)."""
    query_toks = _tokens(query)
    if not query_toks or not entries:
        return {}

    docs = []
    doc_freq: Dict[str, int] = {}
    for e in entries:
        toks = _tokens(e.get("text", ""))
        counts: Dict[str, int] = {}
        for t in toks:
            counts[t] = counts.get(t, 0) + 1
        docs.append((e.get("id"), counts, len(toks)))
        for t in counts:
            doc_freq[t] = doc_freq.get(t, 0) + 1

    n = len(docs)
    avg_len = max(sum(d[2] for d in docs) / n, 1.0)
    raw: Dict[str, float] = {}
    for mid, counts, length in docs:
        score = 0.0
        for qt in query_toks:
            tf = counts.get(qt, 0)
            if not tf:
                continue
            df = doc_freq.get(qt, 0)
            idf = math.log((n - df + 0.5) / (df + 0.5) + 1)
            score += idf * (tf * (K1 + 1)) / (tf + K1 * (1 - B + B * length / avg_len))
        if score > 0 and mid:
            raw[mid] = score

    if not raw:
        return {}
    top = max(raw.values())
    return {mid: s / top for mid, s in raw.items()}


def hybrid_search(
    query: str,
    entries: Sequence[Dict],
    memory_vector=None,
    k: int = 8,
    weights: Tuple[float, float, float] = (0.55, 0.40, 0.05),
    min_score: float = 0.12,
    now: Optional[int] = None,
    vector_rows: Optional[Sequence] = None,
) -> List[Tuple[float, Dict]]:
    """Rank entries for query by fused dense + BM25 + recency score.

    weights = (dense, lexical, recency). Without a healthy vector store the
    dense weight is folded into the lexical term. Gates mirror the deployed
    chat path: a memory needs real relevance (dense or lexical), recency
    alone never qualifies one. Superseded entries never rank.

    vector_rows: pre-fetched memory_vector.search() rows, so a caller that
    needs the raw rows for its own purposes (legacy-row salvage in the
    provider) issues exactly one vector query.
    """
    entries = [e for e in entries
               if isinstance(e, dict) and e.get("id") and not is_superseded(e)]
    if not entries or not query.strip():
        return []

    w_dense, w_lex, w_rec = weights
    vector_scores: Dict[str, float] = {}
    has_vector = memory_vector is not None and getattr(memory_vector, "healthy", False)
    if has_vector:
        try:
            ids = {e["id"] for e in entries}
            rows = (vector_rows if vector_rows is not None
                    else memory_vector.search(query, k=min(k * 3, 20)))
            for r in rows:
                if isinstance(r, dict) and r.get("memory_id") in ids:
                    vector_scores[r["memory_id"]] = max(r.get("score", 0.0), 0.0)
        except Exception:
            has_vector = False

    kw = bm25_scores(query, entries)
    now = now or int(time.time())

    scored = []
    for e in entries:
        mid = e["id"]
        vs = vector_scores.get(mid, 0.0)
        lex = kw.get(mid, 0.0)
        days_old = max((now - e.get("timestamp", 0)) / 86400, 0)
        recency = 1.0 / (1.0 + days_old * 0.05)

        if has_vector:
            if vs < 0.20 and lex < 0.08:
                continue
            final = w_dense * vs + w_lex * lex + w_rec * recency
        else:
            if lex < 0.08:
                continue
            final = (w_dense + w_lex) * lex + w_rec * recency

        if final > min_score:
            scored.append((final, e))

    scored.sort(key=lambda x: (-x[0], x[1].get("id", "")))
    return scored[:k]
