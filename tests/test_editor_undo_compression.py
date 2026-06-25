"""Source-text guards for gallery-editor undo snapshot compression (jdmanring#99).

These lock in the *structure* of the compression scheme — they do not exercise
the async gzip round-trip or undo/redo races, which require a live editor
smoke-test (see the PR notes). They guard the load-bearing correctness
invariants: lossless codec, atomic raw→gz commit, sync-recent / async-deep
restore, generation guard, and safe no-op fallback.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "static/js/galleryEditor.js").read_text(encoding="utf-8")


def _fn(name: str) -> str:
    """Return the body of a top-level `function name(...) { ... }` (brace-matched)."""
    start = _SRC.index(f"function {name}(")
    i = _SRC.index("{", start)
    depth = 0
    for j in range(i, len(_SRC)):
        if _SRC[j] == "{":
            depth += 1
        elif _SRC[j] == "}":
            depth -= 1
            if depth == 0:
                return _SRC[start:j + 1]
    raise AssertionError(f"unbalanced braces for {name}")


# --- Codec: lossless gzip, not lossy-through-canvas PNG ---------------------

def test_uses_gzip_not_png_for_snapshots():
    # PNG via canvas premultiplies alpha (±1 drift on partial-alpha pixels).
    # Snapshot compression must use gzip over the raw bytes (byte-exact).
    assert "new CompressionStream('gzip')" in _SRC
    assert "new DecompressionStream('gzip')" in _SRC
    # The undo codec must NOT route snapshots through toDataURL (lossy alpha).
    assert "_imageDataToPng" not in _SRC and "_pngToImageData" not in _SRC


def test_decompress_rebuilds_imagedata_exactly():
    body = _fn("_decompressSnap")
    assert "_gunzip" in body
    assert "new ImageData(bytes, slot._gzW, slot._gzH)" in body


# --- Compression: atomic commit + safe no-op fallback ----------------------

def test_compress_has_safe_noop_without_compressionstream():
    body = _fn("_compressSnap")
    # If CompressionStream is unavailable, leave snapshots raw (undo still
    # works) — must NOT mark _compressed (that would strand restore with no data).
    assert "typeof CompressionStream !== 'function'" in body
    noop = body.index("typeof CompressionStream !== 'function'")
    ret = body.index("return", noop)
    # The guard returns before any _compressed = true.
    assert "_compressed = true" not in body[noop:ret]


def test_compress_commits_atomically_after_encode():
    body = _fn("_compressSnap")
    # imageData must be nulled only AFTER all bytes are encoded (the commit
    # loop), so a restore racing mid-compression still sees intact raw data.
    encode_pos = body.index("await _gzip(")
    commit_pos = body.index("slot.imageData = null")
    assert encode_pos < commit_pos, "raw imageData nulled before encode completed"
    assert "_compressing" in body  # re-entrancy guard


# --- Restore: sync for recent (raw), async + gen-guard for deep (compressed) -

def test_restore_is_sync_for_raw_and_async_for_compressed():
    body = _fn("_restoreState")
    assert "if (!snap || !snap._compressed) { _applySnap(snap); return; }" in body
    assert "_decompressSnap(snap).then(" in body


def test_restore_generation_guard_drops_stale_decodes():
    body = _fn("_restoreState")
    assert "const gen = ++_restoreGen" in body
    assert "if (gen !== _restoreGen) return;" in body


def test_apply_guards_null_imagedata():
    # A failed/absent decode leaves imageData null; apply must skip it, not throw.
    body = _fn("_applySnap")
    assert "if (s.imageData) layer.ctx.putImageData" in body


# --- Scheduling: deferred to idle, recent window kept raw ------------------

def test_compression_deferred_to_idle_outside_raw_window():
    body = _fn("_scheduleSnapCompression")
    assert "requestIdleCallback" in body
    assert "state.undoStack.length - RAW_RECENT" in body


def test_savestate_schedules_compression():
    body = _fn("_saveState")
    assert "_scheduleSnapCompression()" in body


def test_raw_recent_window_defined():
    assert "const RAW_RECENT = 3" in _SRC
