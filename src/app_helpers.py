# src/app_helpers.py
import base64
import hashlib
import logging
import os
import re

from fastapi import HTTPException
from fastapi.responses import HTMLResponse
from starlette.requests import Request

logger = logging.getLogger(__name__)

def read_if_exists(path: str) -> str:
    """Read file if it exists, return empty string otherwise."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def file_to_data_url(path: str, mime: str) -> str:
    """Convert file to data URL."""
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return f"data:{mime};base64,{b64}"

def abs_join(base_dir: str, rel: str) -> str:
    """Join paths and return absolute path."""
    return os.path.abspath(os.path.join(base_dir, rel))

# (path -> (mtime, hash)) cache for asset content hashes.
_ASSET_VERSION_CACHE: dict = {}

_ASSET_PIN_RE = re.compile(r'(/static/([\w./-]+?))\?v=[\w.-]+')


def _asset_content_version(asset_path: str) -> str:
    """Short content hash for a static asset, cached by mtime."""
    try:
        mtime = os.stat(asset_path).st_mtime_ns
        cached = _ASSET_VERSION_CACHE.get(asset_path)
        if cached and cached[0] == mtime:
            return cached[1]
        with open(asset_path, "rb") as f:
            digest = hashlib.sha1(f.read()).hexdigest()[:12]
        _ASSET_VERSION_CACHE[asset_path] = (mtime, digest)
        return digest
    except OSError:
        return ""


def rewrite_asset_versions(html: str, html_dir: str) -> str:
    """Rewrite every `/static/<asset>?v=<pin>` to a content-hash version.

    The pins used to be hand-maintained, and a forgotten bump meant clients
    kept a stale cached asset indefinitely (a restored stylesheet once looked
    broken for an hour because the pin never changed). Deriving the version
    from file content makes that failure mode structurally impossible: the
    asset changes, the URL changes, the client refetches. Assets that cannot
    be found keep their hand-written pin (fail open, never break the page).
    """
    def _sub(m):
        rel = m.group(2)
        for candidate in (
            os.path.join(html_dir, rel),            # html lives in static/
            os.path.join(html_dir, "static", rel),  # html lives at repo root
        ):
            version = _asset_content_version(candidate)
            if version:
                return f"{m.group(1)}?v={version}"
        return m.group(0)
    return _ASSET_PIN_RE.sub(_sub, html)


def serve_html_with_nonce(request: Request, file_path: str) -> HTMLResponse:
    """Read an app-bundled HTML page and inject the CSP nonce into inline <script> tags.

    Callers pass fixed, server-owned template paths (index/login/backgrounds),
    never a client-supplied path. So any read failure here — a missing file
    (broken deployment) or a permission/IO error — is a server fault, not a
    client "not found": map all of them to a logged 500 so a missing core
    template surfaces in 5xx alerting instead of hiding behind a 404. If a
    future caller serves a client-influenced path where 404 is correct, branch
    that at the call site rather than defaulting this shared helper to 404.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            html = f.read()
    except OSError:
        logger.exception("Failed to read page %s", file_path)
        raise HTTPException(500, "Internal server error")
    nonce = getattr(request.state, "csp_nonce", "")
    html = html.replace("{{CSP_NONCE}}", nonce)
    html = rewrite_asset_versions(html, os.path.dirname(file_path))
    return HTMLResponse(html)


def inside_base_dir(base_dir: str, path: str) -> bool:
    """Check if path is inside base directory."""
    if not isinstance(base_dir, str) or not isinstance(path, str):
        return False
    base = os.path.realpath(base_dir)
    p = os.path.realpath(path)
    try:
        return os.path.commonpath([base, p]) == base
    except Exception:
        return False
