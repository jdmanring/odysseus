#!/usr/bin/env python3
"""End-to-end integration verifier for the memory stack: app code driving a
managed Qdrant SERVER with llama.cpp embeddings, through real writes/searches.

This exercises the exact production path — no mocks, no test doubles:

  src.vector_client.get_vector_client()   -> launches/attaches the Qdrant server
  src.memory_vector.MemoryVectorStore     -> embedding lanes + collections
  src.embeddings (llama.cpp GGUF Q8_0)    -> the unified local backend

Phases (each asserts, the run fails hard on the first broken invariant):

  A. server-mode   The client must be a REMOTE QdrantClient talking to the
                   managed server — not a silent fallback to the single-writer
                   embedded store. This is the assertion that makes the whole
                   OpenBSD source build meaningful.
  B. write/search  Real memory texts embedded by llama.cpp, upserted, and
                   retrieved by a semantic paraphrase query (no term overlap).
  C. concurrent    A SECOND PROCESS opens the same server+collection and does
                   its own write+search while this process's client stays open.
                   This is the motivating failure of embedded mode (the app and
                   the memory MCP subprocess colliding on the storage lock) —
                   it must simply work against the server.
  D. persistence   Stop the server, restart it via ensure_running(), and prove
                   the data written in B and C is still there and searchable.

Isolation: everything runs under a dedicated data dir and port so a live app
(APP_PORT 7000, its own qdrant on 6333) is never touched.

    python3 tooling/verify_memory_integration.py \
        --data-dir /build/memtest --port 6355

Exit 0 = all phases passed. Nonzero = the failing phase is named on stderr.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# Paraphrase queries share no content words with their target memory, so a hit
# proves semantic embedding retrieval, not keyword matching.
MEMORIES = [
    ("mem-cat", "The user's cat is named Biscuit and is afraid of thunderstorms."),
    ("mem-editor", "The user prefers writing code in a terminal-based text editor."),
    ("mem-coffee", "The user drinks two cups of black coffee every morning."),
]
QUERY = "what is the pet called and what scares it"
QUERY_TARGET = "mem-cat"

WORKER_MEMORY = ("mem-worker", "The user's favourite hiking trail follows a river gorge.")
WORKER_QUERY = "which outdoor walking route does the user like best"


def _configure_env(args) -> None:
    """Must run before ANY src.* import — constants bind DATA_DIR at import."""
    os.environ["ODYSSEUS_DATA_DIR"] = args.data_dir
    os.environ["QDRANT_PORT"] = str(args.port)
    os.environ.pop("QDRANT_HOST", None)       # app-managed server, not external
    os.environ.pop("QDRANT_EMBEDDED", None)   # never allow the embedded fallback here
    os.environ.pop("EMBEDDING_URL", None)     # force the local llama.cpp backend
    os.makedirs(args.data_dir, exist_ok=True)


def _fail(phase: str, msg: str) -> None:
    print(f"FAIL [{phase}] {msg}", file=sys.stderr)
    raise SystemExit(1)


def _ok(phase: str, msg: str) -> None:
    print(f"PASS [{phase}] {msg}")


# ---------------------------------------------------------------- phases ----

def phase_a_server_mode(port: int):
    from src.vector_client import get_vector_client
    client = get_vector_client()
    inner = getattr(client._q, "_client", None)
    kind = type(inner).__name__ if inner is not None else type(client._q).__name__
    if "Local" in kind:
        _fail("A server-mode", f"client fell back to embedded store ({kind}) — "
              f"server binary missing or failed to start")
    import socket
    try:
        socket.create_connection(("127.0.0.1", port), timeout=2).close()
    except OSError as e:
        _fail("A server-mode", f"nothing answering on 127.0.0.1:{port}: {e}")
    _ok("A server-mode", f"remote client ({kind}) against managed server on :{port}")
    return client


def phase_b_write_search(data_dir: str):
    from src.embeddings import get_embedding_client, LlamaCppEmbedClient
    emb = get_embedding_client()
    if not isinstance(emb, LlamaCppEmbedClient):
        _fail("B write/search", f"embedding backend is {type(emb).__name__}, "
              f"expected LlamaCppEmbedClient")
    from src.memory_vector import MemoryVectorStore
    store = MemoryVectorStore(data_dir)
    if not store.healthy:
        _fail("B write/search", "MemoryVectorStore reports unhealthy after init")
    for mid, text in MEMORIES:
        store.add(mid, text)
    hits = store.search(QUERY, k=3)
    if not hits:
        _fail("B write/search", f"semantic query returned nothing: {QUERY!r}")
    top = hits[0]
    if top.get("memory_id") != QUERY_TARGET:
        _fail("B write/search", f"top hit is not the target memory: {top!r}")
    _ok("B write/search", f"llama.cpp embed + upsert + paraphrase retrieval "
        f"(top hit {top['memory_id']} score={top['score']})")
    return store


def phase_c_concurrent(args):
    """Second real OS process, same server + same collection, no lock error."""
    cmd = [sys.executable, os.path.abspath(__file__), "--worker",
           "--data-dir", args.data_dir, "--port", str(args.port)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        _fail("C concurrent", f"worker process failed (rc={proc.returncode}):\n"
              f"{proc.stdout}\n{proc.stderr}")
    try:
        result = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception:
        _fail("C concurrent", f"worker emitted no result JSON:\n{proc.stdout}")
    if not result.get("ok"):
        _fail("C concurrent", f"worker reported failure: {result}")
    _ok("C concurrent", f"second process wrote+searched the same collection "
        f"concurrently (top hit id={result['top_id']})")


def worker_main(args) -> None:
    """Runs in the second process: connect, write, search, report JSON."""
    _configure_env(args)
    from src.vector_client import get_vector_client
    client = get_vector_client()
    kind = type(getattr(client._q, "_client", client._q)).__name__
    if "Local" in kind:
        print(json.dumps({"ok": False, "error": f"worker got embedded store {kind}"}))
        raise SystemExit(1)
    from src.memory_vector import MemoryVectorStore
    store = MemoryVectorStore(args.data_dir)
    mid, text = WORKER_MEMORY
    store.add(mid, text)
    hits = store.search(WORKER_QUERY, k=3)
    top_id = hits[0].get("memory_id") if hits else None
    print(json.dumps({"ok": bool(hits) and top_id == mid, "top_id": top_id,
                      "client": kind}))


def phase_d_persistence(args, store):
    from src import qdrant_server
    from src.vector_client import reset_client, get_vector_client
    from src.constants import QDRANT_STORAGE_DIR
    if qdrant_server._proc is None:
        _fail("D persistence", "this process did not launch the server (a leftover "
              "instance owns the port) — kill it and rerun for a clean test")
    qdrant_server.stop()
    reset_client()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not qdrant_server._port_responds("127.0.0.1", args.port):
            break
        time.sleep(0.3)
    else:
        _fail("D persistence", "server still answering after stop()")
    if not qdrant_server.ensure_running("127.0.0.1", args.port, QDRANT_STORAGE_DIR):
        _fail("D persistence", "server failed to restart")
    get_vector_client()
    from src.memory_vector import MemoryVectorStore
    store2 = MemoryVectorStore(args.data_dir)
    hits = store2.search(QUERY, k=3)
    if not hits or hits[0].get("memory_id") != QUERY_TARGET:
        _fail("D persistence", f"phase-B data lost across restart (hits={hits!r})")
    whits = store2.search(WORKER_QUERY, k=3)
    if not whits or whits[0].get("memory_id") != WORKER_MEMORY[0]:
        _fail("D persistence", f"worker's write lost across restart (hits={whits!r})")
    _ok("D persistence", "both processes' writes survived a full server restart")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", required=True,
                    help="dedicated ODYSSEUS_DATA_DIR (real FS, not tmpfs/mfs)")
    ap.add_argument("--port", type=int, default=6355,
                    help="dedicated Qdrant port (default 6355; never the live 6333/7000)")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        worker_main(args)
        return
    _configure_env(args)
    print(f"Memory-stack integration verifier: data={args.data_dir} port={args.port}\n")
    phase_a_server_mode(args.port)
    store = phase_b_write_search(args.data_dir)
    phase_c_concurrent(args)
    phase_d_persistence(args, store)
    from src import qdrant_server
    qdrant_server.stop()
    print("\nALL PHASES PASSED — server-mode memory stack verified end to end.")


if __name__ == "__main__":
    main()
