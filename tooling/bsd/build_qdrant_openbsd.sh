#!/bin/sh
# build_qdrant_openbsd.sh — build the Qdrant vector-store server from source on
# OpenBSD and install it on PATH, so the app-managed server lifecycle
# (src/qdrant_server.py) works there like it does on the platforms with an
# official binary. OpenBSD is a server OS — running Odysseus there is most likely
# as the multi-client remote server, exactly where the concurrent Rust store
# matters and the single-writer embedded store is unacceptable.
#
# Qdrant does not target OpenBSD. Porting it is the standard set of OpenBSD
# large-Rust-project issues (see the rustc OpenBSD platform-support page); each is
# handled below or in patch_qdrant_openbsd.py as a behaviour-preserving change:
#
#   1. Nightly-only std features in the `common`/`segment` crates (as_ref_unchecked,
#      cfg_select!, if-let match guards) — stable rustc rejects them (E0658).
#      patch_qdrant_openbsd.py rewrites them to stable equivalents.
#   2. jemalloc (tikv-jemalloc-sys) does not build on OpenBSD — its vendored
#      configure aborts. OpenBSD disables jemalloc project-wide anyway (system
#      allocator is preferred). patch gates it out of Cargo.toml + the code sites.
#   3. `mincore(2)` was removed from OpenBSD years ago → undefined symbol at final
#      link. patch gates the one residency call (reports Ok(0) on OpenBSD).
#   4. rustc OOMs compiling the heavy release crates under OpenBSD's default 1536M
#      staff-class datasize limit → SIGABRT. We raise the soft limit (ulimit -d)
#      toward the hard cap; no login.conf edit needed where the hard cap is high.
#   5. Fat LTO on the final binary exceeds this host's RAM+swap → SIGABRT. We build
#      with LTO off (CARGO_PROFILE_RELEASE_LTO=off): modest runtime-perf tradeoff
#      for a binary that links.
#   6. Disk: a from-scratch build needs ~2-3 GB of `target/`. On a small partition,
#      set CARGO_TARGET_DIR to a roomier filesystem (see the OpenBSD build runbook,
#      docs/fork/runbooks/openbsd-qdrant-build.md).
#
# This is a LONG one-time compile (tens of minutes). Idempotent: it no-ops if a
# `qdrant` is already on PATH. POSIX sh.

set -e

if command -v qdrant >/dev/null 2>&1; then
    echo "[qdrant-openbsd] qdrant already on PATH ($(command -v qdrant)); nothing to do."
    exit 0
fi

OS="$(uname -s)"
[ "$OS" = "OpenBSD" ] || { echo "[qdrant-openbsd] only for OpenBSD (got $OS)."; exit 0; }

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
QDRANT_VERSION="${QDRANT_VERSION:-v1.18.3}"   # keep in step with qdrant-client / bin_manager
SRC="${QDRANT_SRC:-$HOME/qdrant-src}"
PKG_PATH="${PKG_PATH:-https://cdn.openbsd.org/pub/OpenBSD/$(uname -r)/packages/$(uname -m)/}"
export PKG_PATH

echo "[qdrant-openbsd] installing build deps (rust, cmake, protobuf, git)…"
doas env PKG_PATH="$PKG_PATH" pkg_add -I rust cmake protobuf git >/dev/null 2>&1 || true

if [ ! -f "$SRC/Cargo.toml" ]; then
    echo "[qdrant-openbsd] cloning Qdrant $QDRANT_VERSION…"
    rm -rf "$SRC"
    git clone --depth 1 -b "$QDRANT_VERSION" https://github.com/qdrant/qdrant.git "$SRC"
fi

echo "[qdrant-openbsd] applying stable-Rust patch…"
python3 "$REPO/tooling/bsd/patch_qdrant_openbsd.py" "$SRC"

echo "[qdrant-openbsd] building (this takes tens of minutes)…"
cd "$SRC"
# OpenBSD's default per-process datasize soft limit (staff class, 1536M) is too
# small for rustc compiling the heavy release crates at opt-level=3 — it aborts
# with "memory allocation failed" (SIGABRT). Raise the soft limit toward the hard
# cap (typically far higher). Best-effort: if the hard cap is itself low, warn so
# the OOM is diagnosable rather than silent.
ulimit -d 6291456 2>/dev/null \
    || echo "[qdrant-openbsd] WARNING: could not raise datasize limit; a heavy crate may OOM (raise datasize-max in login.conf)" >&2
# Qdrant's release profile uses fat LTO, whose final-binary link exceeds this host's
# RAM+swap (SIGABRT). Disable LTO for the OpenBSD build — a modest runtime-perf
# tradeoff for a binary that actually links. Keep the profile's codegen-units=1
# (fewer intermediate object files → leaner on a small disk); memory is fine without
# LTO given the raised datasize limit above. Overridden via env, Cargo.toml untouched.
CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}" \
CARGO_PROFILE_RELEASE_LTO="${CARGO_PROFILE_RELEASE_LTO:-off}" \
    cargo build --release --bin qdrant

BIN="$SRC/target/release/qdrant"
[ -x "$BIN" ] || { echo "[qdrant-openbsd] build did not produce $BIN" >&2; exit 1; }

echo "[qdrant-openbsd] installing to /usr/local/bin…"
doas cp "$BIN" /usr/local/bin/qdrant
doas chmod 0755 /usr/local/bin/qdrant

echo "[qdrant-openbsd] done: $(qdrant --version 2>/dev/null || echo /usr/local/bin/qdrant)"
