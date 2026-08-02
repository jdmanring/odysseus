# Qdrant server lifecycle + OpenBSD vector memory: analysis & plan

> **STATUS (2026-07-23): RESOLVED. This doc is the historical analysis; the
> canonical description now lives in [`docs/dev/memory-architecture.md`](../../dev/memory-architecture.md).**
> Embedded local mode is the default (`src/vector_client.py`; `QDRANT_HOST` still
> selects server mode), verified end-to-end on the Linux host and OpenBSD.
> **OpenBSD is NOT blocked**; the "grpcio wall" below was cleared: a system-libs
> grpcio build gets past LibreSSL but dies on grpcio's own `upb`, so instead a
> vendored grpc *import* stub (local mode never uses gRPC) unblocks qdrant-client,
> and the llama.cpp GGUF embedder is built from source. All reproducible via
> `tooling/provision_bsd_memory.sh` (wired into `setup.sh`). The "blocked" notes
> below are superseded.

**Question (2026-07-23):** (A) what would it take to make Odysseus start Qdrant
when it opens and stop it when it closes; (B) can Qdrant be sourced for OpenBSD so
it isn't left keyword-only. Investigated on `develop`, the feature branch
`feat/memory-qdrant-nomic` (`13e17b87`), and live on the OpenBSD 7.9 bench.

## Finding A: the launcher does not exist anywhere

The Qdrant **client + adapter + embedding** layer (`src/vector_client.py`,
`memory_vector.py`, `embeddings.py`, `rag_vector.py`) is already on develop
(byte-identical to the feature branch). What is missing everywhere (develop,
`13e17b87`, and the entire git history) is the **server launcher**:

- No `Popen`/subprocess starts a Qdrant server on develop, in `13e17b87`, in
  `app.py` startup, or in `app_initializer`.
- `vector_client.py:74` raises *"The app starts the bundled Qdrant binary; check
  it launched"*, but this string is **aspirational**. `get_vector_client()` only
  does a TCP port probe then connects in **server mode** (`QdrantClient(host,
  port)`, default `localhost:6333`) to a server nothing starts.
- Live consequence on BSD: nothing on 6333, `MemoryVectorStore DEGRADED:
  Qdrant vector memory unavailable`, memory runs keyword-only.

So the launcher must be **written from scratch**: there is no stub to finish and
no launcher hunk in `13e17b87` to cherry-pick. (A branch *merge* is off the
table regardless: merge-base is ~1157 commits back.)

## Finding B: OpenBSD has no Qdrant server binary; local mode is the path

- Qdrant server is **not packaged on OpenBSD** (`pkg_info -Q qdrant` -> empty) and
  there is no upstream OpenBSD release binary. Building the Rust server from
  source is heavy and unproven (RocksDB and friends).
- qdrant-client has a **local/embedded mode** (`QdrantClient(path=...)`, and
  `:memory:`), a pure-Python engine with no server binary. **Every existing vector
  test runs against it**, and access is **single-process** (only the app; the MCP
  memory server does not touch Qdrant), so local mode would be safe *if it could
  be installed*.
- **But it can't be installed on OpenBSD (verified 2026-07-23).** qdrant-client
  depends on `grpcio`; `grpcio` has **no OpenBSD wheel, is not packaged, and
  fails to build from source** (bundled boringssl/abseil compile fails).
  qdrant-client **1.18.0 imports `grpc` unconditionally**: `--no-deps` +
  `import qdrant_client` -> `ModuleNotFoundError: No module named 'grpc'`. So even
  local mode (which never uses gRPC at runtime) can't load. **OpenBSD is blocked
  at the client layer, not just the server binary.**

### OpenBSD paths (all carry real friction)

1. **Make grpcio build.** Retry with a system-libs build
   (`GRPC_PYTHON_BUILD_SYSTEM_OPENSSL/ZLIB/CARES/RE2/ABSL=1` against OpenBSD
   packages) or an OpenBSD port. Uncertain, long compile. If it works, local mode
   follows for free.
2. **grpc import shim**: a tiny stub `grpc` package to satisfy qdrant-client's
   top-level import (local mode never calls gRPC). Fragile, version-coupled.
3. **A non-Qdrant backend behind the adapter.** `vector_client` is already a
   thin Chroma-shaped facade; a pure-Python store (numpy brute-force / hnswlib /
   sqlite-vss) needing neither Qdrant nor grpcio plugs in behind it. Most robust
   OpenBSD-native path, but new code.
4. **Leave OpenBSD keyword-only**: the current graceful degrade; honest if the
   above aren't worth it for one target.

## The design decision (A and B converge)

| Option | How | Linux/Mac/Win/FreeBSD | OpenBSD | Complexity |
|--------|-----|----|----|-----------|
| **1. Server + launcher** | write launcher, add `qdrant` to `bin_manager.TOOL_MAP`, wire app lifecycle; FreeBSD via `pkg`/`which` | ✅ | ❌ no binary | high (download/pin, start/stop, orphan guard, ordering) |
| **2. Local mode** | `vector_client` uses `QdrantClient(path=QDRANT_STORAGE_DIR)`; delete the server expectation | ✅ | ❌ grpcio won't install | low (no binary, no port, no launcher) |
| **3. Local + OpenBSD backend** | Option 2 everywhere, plus a pure-Python store behind the adapter for OpenBSD | ✅ | ✅ (non-Qdrant) | low + one small backend |

**Recommendation:** **Option 2 (local mode) as the default** resolves A (no
launcher needed; Qdrant access is single-process and the adapter already runs
against the local engine) and gives vector memory on four of five OSes with the
least moving parts. **OpenBSD is a genuinely separate problem** (blocked at the
grpcio/client layer, not just the missing server binary), so it needs its own
decision: (i) invest in a grpcio system-libs build, (ii) a grpc import shim, or
(iii) a small non-Qdrant backend behind the existing adapter (Option 3, the most
robust). If none is worth it for one target, OpenBSD stays keyword-only, which it
already does gracefully. A server + launcher (Option 1) is only worth it if a real
workload proves local mode too slow.

If a server is still wanted (Option 1/3), the itemized work is: new launcher
module (resolve binary -> `Popen` at `QDRANT_STORAGE_DIR` -> readiness wait ->
start/stop), a `qdrant` `TOOL_MAP` entry per platform (`platform.system()`
returns `FreeBSD`/`OpenBSD`, which `bin_manager.get_platform()` does **not**
normalize today; the crux), FreeBSD `pkg`/`which` resolution, `app.py` lifespan
wiring **before** first vector connect (RAG inits at import time, `app.py:588`,
earlier than `_startup_event`), shutdown + orphan guard, and (since **no current
test covers the launch path**) dedicated launcher tests.

## Process (fork rules)

Upstream-candidate (makes Odysseus better). Issue first in `docs/fork/issues/`,
branch from `upstream-mirror`, implement, cherry-pick to develop; branch stays for
the upstream PR. Keep the launcher/mode logic Qt-free so it's testable under the
venv PyQt stub.

## Risks

Startup ordering (import-time RAG init vs lifespan); local-mode performance at
larger vector counts (unmeasured); grpcio build friction on OpenBSD; and the
existing green suite gives **zero** coverage of any server-launch path. Evidence-
gate it (prove the child spawns / local store persists by logged signature).
