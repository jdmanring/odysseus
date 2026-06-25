"""Guards against the editor creating a 0-byte broken gallery image (jdmanring#101).

Both save paths (ge-save 'replace original' and exportToGallery 'save copy')
must refuse to upload an empty (0x0) flattened canvas or a trivially-small blob,
surfacing an error instead of writing a broken 0-byte gallery entry.
"""
from pathlib import Path

_SRC = (Path(__file__).resolve().parents[1] / "static/js/galleryEditor.js").read_text(encoding="utf-8")


def test_flatten_for_save_guard_exists():
    # The helper rejects an empty (0x0) flattened canvas before encoding.
    assert "function _flattenForSave()" in _SRC
    start = _SRC.index("function _flattenForSave()")
    body = _SRC[start:start + 400]
    assert "!flat.width || !flat.height" in body
    assert "throw new Error" in body


def test_both_save_paths_use_the_guard():
    # Neither save handler may call raw flatten() — both must go through the
    # empty-canvas guard. (The only raw flatten() left is inside the helper.)
    assert _SRC.count("const flat = _flattenForSave();") == 2
    assert _SRC.count("const flat = flatten();") == 1  # the helper's own call


def test_both_save_paths_reject_empty_blob():
    # toBlob must reject an empty/trivial blob so an empty encode never uploads.
    assert _SRC.count("b.size > 64") == 2
    assert _SRC.count("Save produced an empty image") == 2
    # The old unconditional encode-failure-only check must be gone.
    assert "reject(new Error('Canvas encode failed'))" not in _SRC
