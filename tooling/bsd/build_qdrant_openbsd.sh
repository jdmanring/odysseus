#!/bin/sh
# build_qdrant_openbsd.sh — build the Qdrant vector-store server from source on
# OpenBSD and install it on PATH, so the app-managed server lifecycle
# (src/qdrant_server.py) works there like it does on the platforms with an
# official binary. OpenBSD is a server OS — running Odysseus there is most likely
# as the multi-client remote server, exactly where the concurrent Rust store
# matters and the single-writer embedded store is unacceptable.
#
# Qdrant does not target OpenBSD: its `common` crate uses three nightly-only std
# features that OpenBSD's packaged stable rustc rejects. patch_qdrant_openbsd.py
# rewrites them to behaviour-identical stable equivalents. Everything else builds
# clean.
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
CARGO_BUILD_JOBS="${CARGO_BUILD_JOBS:-2}" cargo build --release --bin qdrant

BIN="$SRC/target/release/qdrant"
[ -x "$BIN" ] || { echo "[qdrant-openbsd] build did not produce $BIN" >&2; exit 1; }

echo "[qdrant-openbsd] installing to /usr/local/bin…"
doas cp "$BIN" /usr/local/bin/qdrant
doas chmod 0755 /usr/local/bin/qdrant

echo "[qdrant-openbsd] done: $(qdrant --version 2>/dev/null || echo /usr/local/bin/qdrant)"
