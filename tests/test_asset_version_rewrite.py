"""Content-derived cache-busters for static asset pins (defect D3 class).

Hand-maintained ?v= pins meant a forgotten bump left every client on a stale
cached asset. serve_html_with_nonce now rewrites pins to a content hash at
serve time; these tests pin the mechanism and the live wiring.
"""
from pathlib import Path

from src.app_helpers import rewrite_asset_versions, _asset_content_version

REPO = Path(__file__).resolve().parent.parent


def test_pin_rewritten_to_content_hash(tmp_path):
    (tmp_path / "style.css").write_text("body{color:red}", encoding="utf-8")
    html = '<link rel="stylesheet" href="/static/style.css?v=20260630stale">'
    out = rewrite_asset_versions(html, str(tmp_path))
    assert "?v=20260630stale" not in out
    v1 = out.split("?v=")[1].split('"')[0]
    assert len(v1) == 12

    # content change MUST change the URL (this is the whole point)
    (tmp_path / "style.css").write_text("body{color:blue}", encoding="utf-8")
    out2 = rewrite_asset_versions(html, str(tmp_path))
    v2 = out2.split("?v=")[1].split('"')[0]
    assert v1 != v2


def test_unchanged_content_keeps_stable_url(tmp_path):
    (tmp_path / "app.js").write_text("export {}", encoding="utf-8")
    html = '<script src="/static/app.js?v=old"></script>'
    assert rewrite_asset_versions(html, str(tmp_path)) == rewrite_asset_versions(html, str(tmp_path))


def test_missing_asset_fails_open(tmp_path):
    html = '<link href="/static/nonexistent.css?v=handpin">'
    assert rewrite_asset_versions(html, str(tmp_path)) == html


def test_repo_root_fallback(tmp_path):
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "style.css").write_text("x", encoding="utf-8")
    html = '<link href="/static/style.css?v=old">'
    out = rewrite_asset_versions(html, str(tmp_path))
    assert "?v=old" not in out


def test_real_index_pins_are_rewritable():
    """Every ?v= pin in the shipped index.html must resolve to a real asset —
    otherwise it silently keeps a hand pin and reintroduces the stale-cache
    failure mode."""
    html = (REPO / "static" / "index.html").read_text(encoding="utf-8")
    import re
    pins = re.findall(r'/static/([\w./-]+?)\?v=', html)
    assert pins, "expected at least one pinned asset in index.html"
    for rel in pins:
        assert (REPO / "static" / rel).exists(), f"pinned asset missing: {rel}"
        assert _asset_content_version(str(REPO / "static" / rel)), rel


def test_serving_path_is_wired():
    src = (REPO / "src" / "app_helpers.py").read_text(encoding="utf-8")
    body = src.split("def serve_html_with_nonce", 1)[1]
    assert "rewrite_asset_versions(" in body, "serve_html_with_nonce must rewrite asset pins"
