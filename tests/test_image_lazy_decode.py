"""Source-text guards for lazy/async image decoding (jdmanring#98).

Off-screen images in stacked/grid layouts must lazy-load and async-decode so a
long document or a draft grid doesn't decode every bitmap at once. Focus/detail
images must stay eager (lazy would delay the image the user is looking at).
"""
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_DOC = (_REPO / "static/js/document.js").read_text(encoding="utf-8")
_GAL = (_REPO / "static/js/gallery.js").read_text(encoding="utf-8")


def _doc_page_img_block() -> str:
    """The document page-image creation block (the tall full-page PNG stack)."""
    anchor = "/api/document/${docId}/page/${page.page}.png"
    start = _DOC.index(anchor)
    return _DOC[start:start + 400]


def test_document_page_images_lazy_and_async():
    block = _doc_page_img_block()
    assert "img.loading = 'lazy'" in block, "document page images must lazy-load"
    assert "img.decoding = 'async'" in block, "document page images must async-decode"


def test_gallery_draft_thumb_lazy():
    # The draft-thumbnail grid renders many off-screen thumbs at once.
    idx = _GAL.index('class="gallery-editor-draft-thumb" src=')
    tag = _GAL[idx:idx + 160]
    assert 'loading="lazy"' in tag, "gallery draft thumbnails must lazy-load"
    assert 'decoding="async"' in tag


def test_gallery_main_grid_still_lazy():
    # Regression: the main gallery grids were already lazy; keep them so.
    assert _GAL.count('loading="lazy"') >= 3


def test_gallery_detail_image_stays_eager():
    # The detail/focus image is what the user is actively viewing — it must NOT
    # be lazy (that would defer the very image being opened).
    idx = _GAL.index('id="gallery-detail-img" src=')
    # Inspect the <img ...> tag for the detail image (stop at the closing />).
    tag = _GAL[idx:_GAL.index("/>", idx) + 2]
    assert 'loading="lazy"' not in tag, "detail/focus image must stay eager"
