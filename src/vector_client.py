"""
vector_client.py

Qdrant-backed vector store, shaped to the ChromaDB collection API the rest of the
codebase already speaks. This is an adapter, not a general abstraction: there is
exactly one backend (Qdrant), and the job is to preserve the call sites' existing
contract (`get_collection` / `get_or_create_collection` / `delete_collection`, and
collection `.count/.get/.add/.upsert/.delete/.query`) so the migration off Chroma
touches those consumers as little as possible.

Two contract details matter and are handled here so callers don't have to:

- Distance vs. similarity. Chroma's cosine metric returns a *distance* (0 == a
  perfect match) and callers derive `similarity = 1 - distance`. Qdrant's Cosine
  returns a *similarity score* (1 == perfect). `query()` converts back to a Chroma
  distance (`1 - score`) so the existing `1 - distance` formulas stay correct.
- Point IDs. Chroma accepts arbitrary string IDs; Qdrant points must be an unsigned
  int or a UUID. Each caller ID is mapped to a deterministic UUIDv5 and the original
  string is round-tripped in the payload under `_ID_KEY`, so `.get`/`.query` return
  the caller's IDs unchanged.
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# Payload keys reserved by the adapter. Everything else in a point's payload is
# the caller's metadata, returned verbatim as Chroma "metadatas".
_ID_KEY = "_chroma_id"
_DOC_KEY = "_document"

# Stable namespace so a given caller ID always maps to the same Qdrant point ID.
_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")

_client = None
_lock = threading.Lock()


def _point_id(chroma_id: str) -> str:
    return str(uuid.uuid5(_ID_NAMESPACE, chroma_id))


def _port_open(host: str, port: int, timeout: float = 0.5) -> bool:
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
    finally:
        del start


def get_vector_client():
    """Process-wide Qdrant client adapter. Mirrors chroma_client.get_chroma_client:
    reads QDRANT_HOST / QDRANT_PORT (default localhost:6333) and caches one client."""
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client
        host = os.environ.get("QDRANT_HOST", "localhost")
        port = int(os.environ.get("QDRANT_PORT", "6333"))
        if not _port_open(host, port):
            raise RuntimeError(
                f"Qdrant is not reachable at {host}:{port}. The app starts the "
                f"bundled Qdrant binary; check it launched (see logs)."
            )
        from qdrant_client import QdrantClient

        _client = _ClientAdapter(QdrantClient(host=host, port=port))
        return _client


def reset_client() -> None:
    global _client
    with _lock:
        _client = None


class _ClientAdapter:
    """Chroma-client-shaped facade over qdrant_client.QdrantClient."""

    def __init__(self, qdrant):
        self._q = qdrant

    def _exists(self, name: str) -> bool:
        try:
            return self._q.collection_exists(name)
        except Exception:
            return False

    def get_collection(self, name: str) -> "_Collection":
        # Chroma raises when the collection is absent; callers rely on that to
        # branch into get_or_create. Preserve it.
        if not self._exists(name):
            raise ValueError(f"Collection {name} does not exist")
        return _Collection(self._q, name)

    def get_or_create_collection(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> "_Collection":
        from qdrant_client import models

        dim = int((metadata or {}).get("embedding_dimension") or 0)
        if self._exists(name):
            existing_dim = _Collection(self._q, name).dimension
            if dim and existing_dim and existing_dim != dim:
                # Model/dimension changed. Nothing persists worth preserving (the
                # store was non-functional before this migration), so drop and
                # recreate rather than re-embed. See docs/dev/memory-architecture.md.
                logger.info(
                    "Recreating collection %s: dimension %s -> %s",
                    name, existing_dim, dim,
                )
                self._q.delete_collection(name)
            else:
                return _Collection(self._q, name)
        if not dim:
            raise ValueError(
                f"Cannot create collection {name} without embedding_dimension metadata"
            )
        self._q.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=dim, distance=models.Distance.COSINE),
        )
        logger.info("Created Qdrant collection %s (dim=%s, cosine)", name, dim)
        return _Collection(self._q, name)

    def delete_collection(self, name: str) -> None:
        try:
            self._q.delete_collection(name)
        except Exception as e:
            logger.warning("delete_collection(%s) failed: %s", name, e)


class _Collection:
    """Chroma-collection-shaped facade over one Qdrant collection."""

    def __init__(self, qdrant, name: str):
        self._q = qdrant
        self.name = name

    # -- introspection -------------------------------------------------------

    @property
    def dimension(self) -> Optional[int]:
        try:
            info = self._q.get_collection(self.name)
            params = info.config.params.vectors
            # Unnamed single vector -> VectorParams; named -> dict.
            size = getattr(params, "size", None)
            if size is None and isinstance(params, dict):
                size = next(iter(params.values())).size
            return int(size) if size else None
        except Exception:
            return None

    @property
    def metadata(self) -> Dict[str, Any]:
        # Only the dimension is reconstructable from Qdrant; that's all the reset
        # logic needs now that fingerprint-based preservation is gone.
        return {"embedding_dimension": self.dimension}

    def count(self) -> int:
        try:
            return int(self._q.count(self.name, exact=True).count)
        except Exception:
            return 0

    # -- filters -------------------------------------------------------------

    def _filter(self, where: Optional[Dict[str, Any]]):
        if not where:
            return None
        from qdrant_client import models

        conditions = [
            models.FieldCondition(key=k, match=models.MatchValue(value=v))
            for k, v in where.items()
        ]
        return models.Filter(must=conditions)

    # -- writes --------------------------------------------------------------

    def add(
        self,
        ids: Sequence[str],
        documents: Optional[Sequence[str]] = None,
        metadatas: Optional[Sequence[Dict[str, Any]]] = None,
        embeddings: Optional[Sequence[Sequence[float]]] = None,
    ) -> None:
        from qdrant_client import models

        documents = list(documents or [])
        metadatas = list(metadatas or [])
        embeddings = [list(v) for v in (embeddings or [])]
        points = []
        for i, cid in enumerate(ids):
            payload = dict(metadatas[i]) if i < len(metadatas) and metadatas[i] else {}
            payload[_ID_KEY] = cid
            payload[_DOC_KEY] = documents[i] if i < len(documents) else ""
            points.append(
                models.PointStruct(id=_point_id(cid), vector=embeddings[i], payload=payload)
            )
        if points:
            self._q.upsert(self.name, points=points, wait=True)

    # Chroma's upsert and add differ only in overwrite semantics; Qdrant upsert
    # overwrites by point ID either way, so one implementation covers both.
    upsert = add

    def update(
        self,
        ids: Sequence[str],
        documents: Optional[Sequence[str]] = None,
        metadatas: Optional[Sequence[Dict[str, Any]]] = None,
        embeddings: Optional[Sequence[Sequence[float]]] = None,
    ) -> None:
        # Chroma's update() edits existing points in place without changing their
        # IDs (used by VectorRAG.rename_owner to rewrite `owner` metadata). Qdrant's
        # set_payload is a *merge*, so the reserved keys the adapter round-trips
        # (_ID_KEY, _DOC_KEY) survive automatically — metadatas carry only user
        # fields — while update_vectors handles the rare embedding change.
        documents = list(documents or [])
        metadatas = list(metadatas or [])
        embeddings = [list(v) for v in (embeddings or [])]
        for i, cid in enumerate(ids):
            pid = _point_id(cid)
            payload: Dict[str, Any] = (
                dict(metadatas[i]) if i < len(metadatas) and metadatas[i] else {}
            )
            if i < len(documents):
                payload[_DOC_KEY] = documents[i]
            if payload:
                self._q.set_payload(self.name, payload=payload, points=[pid], wait=True)
            if i < len(embeddings) and embeddings[i]:
                from qdrant_client import models

                self._q.update_vectors(
                    self.name,
                    points=[models.PointVectors(id=pid, vector=embeddings[i])],
                    wait=True,
                )

    def delete(self, ids: Sequence[str]) -> None:
        self._q.delete(self.name, points_selector=[_point_id(c) for c in ids], wait=True)

    # -- reads ---------------------------------------------------------------

    def _row(self, point) -> Dict[str, Any]:
        payload = point.payload or {}
        meta = {k: v for k, v in payload.items() if k not in (_ID_KEY, _DOC_KEY)}
        return {
            "id": payload.get(_ID_KEY, str(point.id)),
            "document": payload.get(_DOC_KEY, ""),
            "metadata": meta,
            "embedding": getattr(point, "vector", None),
        }

    def get(
        self,
        ids: Optional[Sequence[str]] = None,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        include = list(include or [])
        want_vectors = "embeddings" in include
        rows: List[Dict[str, Any]] = []
        if ids is not None:
            found = self._q.retrieve(
                self.name,
                ids=[_point_id(c) for c in ids],
                with_payload=True,
                with_vectors=want_vectors,
            )
            rows = [self._row(p) for p in found]
        else:
            offset = None
            while True:
                batch, offset = self._q.scroll(
                    self.name,
                    scroll_filter=self._filter(where),
                    limit=256,
                    with_payload=True,
                    with_vectors=want_vectors,
                    offset=offset,
                )
                rows.extend(self._row(p) for p in batch)
                if offset is None:
                    break
        out = {
            "ids": [r["id"] for r in rows],
            "documents": [r["document"] for r in rows],
            "metadatas": [r["metadata"] for r in rows],
        }
        if want_vectors:
            out["embeddings"] = [r["embedding"] for r in rows]
        return out

    def query(
        self,
        query_embeddings: Sequence[Sequence[float]],
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        include: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        include = list(include or [])
        want_vectors = "embeddings" in include
        qfilter = self._filter(where)
        ids: List[List[str]] = []
        distances: List[List[float]] = []
        documents: List[List[str]] = []
        metadatas: List[List[Dict[str, Any]]] = []
        embeddings: List[List[Any]] = []
        for vec in query_embeddings:
            hits = self._q.query_points(
                self.name,
                query=list(vec),
                limit=n_results,
                query_filter=qfilter,
                with_payload=True,
                with_vectors=want_vectors,
            ).points
            row_ids, row_dist, row_docs, row_meta, row_vec = [], [], [], [], []
            for h in hits:
                r = self._row(h)
                row_ids.append(r["id"])
                # Qdrant Cosine returns a similarity score (1 == identical); Chroma
                # callers expect a distance and compute `1 - distance`. Convert.
                row_dist.append(1.0 - float(h.score))
                row_docs.append(r["document"])
                row_meta.append(r["metadata"])
                row_vec.append(r["embedding"])
            ids.append(row_ids)
            distances.append(row_dist)
            documents.append(row_docs)
            metadatas.append(row_meta)
            embeddings.append(row_vec)
        out = {
            "ids": ids,
            "distances": distances,
            "documents": documents,
            "metadatas": metadatas,
        }
        if want_vectors:
            out["embeddings"] = embeddings
        return out
