import fnmatch
import logging
import os
import requests
from typing import List, Tuple, Optional
from huggingface_hub import HfApi

logger = logging.getLogger(__name__)


class HfUrlResolver:
    """Resolves Hugging Face repository files to direct download URLs."""

    def __init__(self, token: Optional[str] = None):
        self.api = HfApi(token=token)

    def get_commit_hash(self, repo_id: str) -> Optional[str]:
        """Return the current HEAD commit SHA for repo_id's main branch, or None on failure."""
        try:
            info = self.api.model_info(repo_id)
            return info.sha or None
        except Exception:
            return None

    def resolve_snapshot_urls(
        self, repo_id: str, include: Optional[str] = None
    ) -> Tuple[List[Tuple[str, str, int]], str]:
        """Return (url, relative_path, size_bytes) for all files in a repo snapshot.

        URLs are pinned to the current HEAD commit hash for reproducibility.
        size_bytes is 0 when the API cannot provide it.
        Three fallbacks are tried in order: list_repo_tree (preferred — returns sizes),
        list_repo_files (no sizes), then the raw HF API tree endpoint.
        """
        logger.debug("Resolving files for %s (token: %s)", repo_id, bool(self.api.token))
        commit = self.get_commit_hash(repo_id) or "main"

        file_entries: List[Tuple[str, int]] = []

        # Primary: list_repo_tree returns sizes in a single call.
        try:
            items = list(self.api.list_repo_tree(repo_id, recursive=True))
            file_entries = [
                (item.rfilename, item.size or 0)
                for item in items
                if getattr(item, "size", None) is not None
            ]
            logger.debug("list_repo_tree: %d files", len(file_entries))
        except Exception as e:
            logger.warning("list_repo_tree failed for %s: %s", repo_id, e)

        # Fallback 1: list_repo_files — paths only, no sizes.
        if not file_entries:
            try:
                paths = list(self.api.list_repo_files(repo_id))
                file_entries = [(p, 0) for p in paths]
                logger.debug("list_repo_files fallback: %d files (sizes unavailable)", len(file_entries))
            except Exception as e:
                logger.warning("list_repo_files failed for %s: %s", repo_id, e)

        # Fallback 2: raw HF API tree endpoint — returns sizes in JSON.
        if not file_entries:
            try:
                headers = {}
                if self.api.token:
                    headers["Authorization"] = f"Bearer {self.api.token}"
                resp = requests.get(
                    f"https://huggingface.co/api/models/{repo_id}/tree/main",
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    file_entries = [
                        (item["path"], item.get("size", 0))
                        for item in resp.json()
                        if item.get("type") == "file"
                    ]
                    logger.debug("API tree fallback: %d files", len(file_entries))
                else:
                    logger.warning("API tree fallback returned %d for %s", resp.status_code, repo_id)
            except Exception as e:
                logger.warning("API tree fallback failed for %s: %s", repo_id, e)

        if include:
            filtered = [
                (p, sz) for p, sz in file_entries
                if fnmatch.fnmatch(p, include) or fnmatch.fnmatch(os.path.basename(p), include)
            ]
            logger.debug("Filter '%s': %d → %d files", include, len(file_entries), len(filtered))
            file_entries = filtered

        seen: set = set()
        urls: List[Tuple[str, str, int]] = []
        for path, size in file_entries:
            url = f"https://huggingface.co/{repo_id}/resolve/{commit}/{path}"
            if url not in seen:
                urls.append((url, path, size))
                seen.add(url)
        return urls, commit
