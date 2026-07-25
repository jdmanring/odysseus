"""Write-time supersede for memory entries.

Why this exists (measured): embedding models cannot rank a current fact above
its outdated predecessor at query time — the stale section of the memory
retrieval benchmark fails for all 18 models tested (best 0.67, most below
0.55). The fix is architectural, at write time: when a new memory updates an
old one, the old one must stop competing in semantic search at all.

Why supersede is NOT fully automatic: doc-doc cosine (production nomic Q8_0
embedder, search_document prefix both sides) does not separate true
supersede pairs from distinct-but-similar facts. Measured on the benchmark's
labeled pairs (2026-07-25, 24 supersede / 30 trap / 552 cross pairs):

    class                          min    median  max
    true supersede (new vs old)    0.698  0.768   0.880
    trap (similar wording, both
      facts must survive)          0.583  0.690   0.754
    cross (unrelated facts)        0.468  0.613   0.760

    threshold  supersede-recall  trap-FP  cross-FP
    0.70       0.96              0.400    0.049
    0.80       0.33              0.000    0.000

At any threshold with useful recall the false-positive rate on distinct
facts is unacceptable (a false supersede silently hides a real memory), so:

  * AUTO tier (>= 0.80): zero measured false positives. Applied silently on
    write — this catches near-restatements and direct updates.
  * SUGGEST tier (0.70-0.80): candidates are returned to the writer. The
    caller (the agent writing "user switched to green tea", the API client)
    is the one party that knows whether the new fact replaces the old one;
    it confirms with an explicit supersede call.

Superseded entries keep their JSON record (superseded_by / superseded_at —
history is never destroyed) but are removed from the vector index and
filtered from keyword fallback, so they can no longer outrank the current
fact. Thresholds are model-specific: re-run the threshold probe if the
embedding model ever changes.

Env knobs: ODYSSEUS_MEMORY_SUPERSEDE=0 disables the whole mechanism;
ODYSSEUS_MEMORY_SUPERSEDE_AUTO / _SUGGEST override the thresholds.
"""

import logging
import os
import time
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

AUTO_THRESHOLD = 0.80
SUGGEST_THRESHOLD = 0.70


def _enabled() -> bool:
    return os.getenv("ODYSSEUS_MEMORY_SUPERSEDE", "1") not in ("0", "false", "no")


def _thresholds() -> tuple:
    try:
        auto = float(os.getenv("ODYSSEUS_MEMORY_SUPERSEDE_AUTO", AUTO_THRESHOLD))
    except ValueError:
        auto = AUTO_THRESHOLD
    try:
        suggest = float(os.getenv("ODYSSEUS_MEMORY_SUPERSEDE_SUGGEST", SUGGEST_THRESHOLD))
    except ValueError:
        suggest = SUGGEST_THRESHOLD
    return auto, suggest


def is_superseded(entry: Dict) -> bool:
    """True when an entry has been superseded and must not be retrieved."""
    return bool(isinstance(entry, dict) and entry.get("superseded_by"))


def apply(memory_manager, memory_vector, new_id: str, old_ids: List[str],
          owner: Optional[str] = None) -> List[str]:
    """Mark old_ids as superseded by new_id. Validates each candidate:
    it must exist, must not be the new entry itself, must not already be
    superseded, and (when owner is given) must belong to the same owner.
    Returns the ids actually superseded."""
    if not old_ids:
        return []
    entries = memory_manager.load_all()
    by_id = {e.get("id"): e for e in entries if isinstance(e, dict)}
    now = int(time.time())
    applied = []
    for old_id in old_ids:
        entry = by_id.get(old_id)
        if entry is None or old_id == new_id or is_superseded(entry):
            continue
        if owner is not None and entry.get("owner") != owner:
            continue
        entry["superseded_by"] = new_id
        entry["superseded_at"] = now
        applied.append(old_id)
    if not applied:
        return []
    memory_manager.save(entries)
    if memory_vector is not None and getattr(memory_vector, "healthy", False):
        for old_id in applied:
            try:
                memory_vector.remove(old_id)
            except Exception as e:
                logger.warning("supersede: vector remove failed for %s: %s", old_id, e)
    logger.info("memory supersede: %s replaces %s", new_id, applied)
    return applied


def on_write(memory_manager, memory_vector, entry: Dict) -> Dict:
    """Run supersede detection for a freshly written entry.

    Returns {"superseded": [ids auto-applied], "candidates": [{"id", "text",
    "similarity"}, ...]} — candidates are the SUGGEST-tier matches the caller
    should surface for explicit confirmation. Never raises: on any failure
    the write stands and this returns empty results.
    """
    result = {"superseded": [], "candidates": []}
    if not _enabled() or not isinstance(entry, dict):
        return result
    if memory_vector is None or not getattr(memory_vector, "healthy", False):
        return result
    text = (entry.get("text") or "").strip()
    new_id = entry.get("id")
    if not text or not new_id:
        return result

    auto_th, suggest_th = _thresholds()
    try:
        matches = memory_vector.similar(text, k=5, floor=suggest_th)
    except Exception as e:
        logger.warning("supersede detection failed: %s", e)
        return result

    entries = memory_manager.load_all()
    by_id = {e.get("id"): e for e in entries if isinstance(e, dict)}
    owner = entry.get("owner")

    auto_ids = []
    for m in matches:
        mid = m.get("memory_id")
        old = by_id.get(mid)
        if old is None or mid == new_id or is_superseded(old):
            continue
        if old.get("owner") != owner:
            continue
        if m.get("similarity", 0.0) >= auto_th:
            auto_ids.append(mid)
        else:
            result["candidates"].append({
                "id": mid,
                "text": old.get("text", ""),
                "similarity": round(float(m.get("similarity", 0.0)), 3),
            })

    if auto_ids:
        result["superseded"] = apply(
            memory_manager, memory_vector, new_id, auto_ids, owner=owner
        )
    return result
