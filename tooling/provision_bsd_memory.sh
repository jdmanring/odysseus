#!/bin/sh
# provision_bsd_memory.sh — make the local, self-contained memory stack build on
# FreeBSD and OpenBSD, where the default Linux/macOS/Windows path does not.
#
# The default stack is `fastembed` (ONNX embeddings via onnxruntime) + a
# `qdrant-client` talking to Qdrant. On the BSDs two things are missing from PyPI:
#
#   * onnxruntime has no BSD wheel and no BSD support at all → fastembed can't run.
#     The app already falls back to a llama.cpp GGUF backend running the SAME nomic
#     model; llama.cpp is small and portable and compiles from source here.
#   * grpcio (a hard import of qdrant-client) has no OpenBSD wheel and its bundled
#     upb fails to compile. The app uses qdrant-client's LOCAL, in-process store,
#     which never speaks gRPC — so a tiny import stub satisfies it (see
#     tooling/bsd/grpc_stub).
#
# This script installs exactly those pieces. It is idempotent: every step is
# guarded by an import check, so re-running is a no-op once the stack is healthy.
# setup.sh calls it on BSD; it can also be run standalone. POSIX sh (OpenBSD /bin/sh).
#
# Note: the general server deps (fastapi, uvicorn, sqlalchemy, numpy, …) come from
# the OS package manager into a --system-site-packages venv; this script covers
# only the memory/embedding pieces that need special handling on BSD.

set -e

OS="$(uname -s)"
case "$OS" in
    FreeBSD | OpenBSD) : ;;
    *) echo "provision_bsd_memory.sh: only needed on FreeBSD/OpenBSD (got $OS); nothing to do." ; exit 0 ;;
esac

REPO="$(cd "$(dirname "$0")/.." && pwd)"
PY="$REPO/venv/bin/python"
PIP="$PY -m pip"
[ -x "$PY" ] || { echo "ERROR: venv not found at $REPO/venv — run setup.sh first." >&2; exit 1; }
SP="$("$PY" -c 'import site; print(site.getsitepackages()[0])')"

log() { echo "[bsd-memory] $*"; }
have() { "$PY" -c "import $1" 2>/dev/null; }

# --- 1. qdrant-client (vector store client), grpcio-free --------------------
if ! have qdrant_client; then
    log "installing qdrant-client without grpcio (grpcio has no BSD path)"
    $PIP install --no-deps --quiet qdrant-client
    # qdrant-client's pure-Python deps (numpy comes from the system pkg):
    $PIP install --quiet httpx urllib3 portalocker pydantic protobuf pydantic-settings
fi
if ! have grpc; then
    log "installing grpc import stub (local mode uses no gRPC at runtime)"
    mkdir -p "$SP/grpc"
    cp "$REPO/tooling/bsd/grpc_stub/grpc/__init__.py" "$SP/grpc/__init__.py"
fi

# --- 2. llama.cpp GGUF embedding backend (fastembed/onnxruntime absent) -----
if ! have llama_cpp; then
    log "building llama-cpp-python from source (this compiles llama.cpp; takes a while)"
    CMAKE_ARGS="-DGGML_NATIVE=OFF -DGGML_OPENMP=OFF" FORCE_CMAKE=1 \
        $PIP install --no-cache-dir --quiet llama-cpp-python
fi
# OpenBSD-only: the loader's platform allowlist names linux/freebsd but not
# openbsd, even though openbsd loads .so exactly like them. Add it.
if [ "$OS" = "OpenBSD" ]; then
    EXT="$SP/llama_cpp/_ctypes_extensions.py"
    if [ -f "$EXT" ] && ! grep -q 'startswith("openbsd")' "$EXT"; then
        log "patching llama_cpp loader to recognise OpenBSD (.so branch)"
        sed -i 's/or sys.platform.startswith("freebsd"):/or sys.platform.startswith("freebsd") or sys.platform.startswith("openbsd"):/' "$EXT"
    fi
fi
# BSD linkers leave the shared libs versioned (libX.so.N) without the unversioned
# libX.so symlink the ctypes loader looks up. Create them if missing.
LIBDIR="$SP/llama_cpp/lib"
if [ -d "$LIBDIR" ]; then
    for base in libllama libggml libggml-base libggml-cpu libmtmd; do
        if [ ! -e "$LIBDIR/$base.so" ]; then
            v=$(ls "$LIBDIR/$base".so.* 2>/dev/null | grep -E '\.so\.[0-9]+$' | head -1)
            [ -n "$v" ] && ln -sf "$(basename "$v")" "$LIBDIR/$base.so" && log "linked $base.so -> $(basename "$v")"
        fi
    done
fi

# --- 3. huggingface-hub to fetch the nomic GGUF, minus the Rust hf-xet dep ---
if ! have huggingface_hub; then
    log "installing huggingface-hub without hf-xet (its Rust accelerator won't build here)"
    $PIP install --no-deps --quiet huggingface-hub
    $PIP install --quiet filelock fsspec packaging pyyaml requests tqdm typing-extensions
fi

# --- verify -----------------------------------------------------------------
if "$PY" - <<'PYCHK'
import sys
import qdrant_client, llama_cpp, huggingface_hub  # noqa: F401
# Exercise local-mode Qdrant end-to-end (no server, no gRPC).
import tempfile
from qdrant_client import QdrantClient, models
d = tempfile.mkdtemp()
c = QdrantClient(path=d)
c.create_collection("_probe", vectors_config=models.VectorParams(size=2, distance=models.Distance.COSINE))
c.upsert("_probe", points=[models.PointStruct(id=1, vector=[1.0, 0.0], payload={})])
assert c.query_points("_probe", query=[1.0, 0.0], limit=1).points[0].id == 1
c.close()
print("[bsd-memory] OK: qdrant local mode + llama_cpp + huggingface_hub all import and run")
PYCHK
then
    exit 0
else
    echo "[bsd-memory] FAILED verification — memory will run keyword-only until fixed." >&2
    exit 1
fi
