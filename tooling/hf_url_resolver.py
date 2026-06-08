import os
from typing import List, Tuple, Optional
from huggingface_hub import HfApi

class HfUrlResolver:
    """
    Resolves Hugging Face repository files to direct download URLs.
    """

    def __init__(self, token: Optional[str] = None):
        self.api = HfApi(token=token)

    def get_commit_hash(self, repo_id: str) -> Optional[str]:
        """Return the current HEAD commit SHA for repo_id's main branch, or None on failure."""
        try:
            info = self.api.model_info(repo_id)
            return info.sha or None
        except Exception:
            return None

    def resolve_snapshot_urls(self, repo_id: str, include: Optional[str] = None) -> List[Tuple[str, str]]:
        """
        Returns a list of (url, relative_path) for all files in a repo snapshot.
        URLs are pinned to the current HEAD commit hash so they are reproducible
        and so the HF library recognises the downloaded files as a valid cache entry.
        """
        # Fetch commit hash first; fall back to 'main' branch ref if unavailable
        # (private repo without token, network error, etc.)
        commit = self.get_commit_hash(repo_id) or "main"

        files = list(self.api.list_repo_files(repo_id))

        if include:
            import fnmatch
            files = [f for f in files if fnmatch.fnmatch(f, include)]

        urls = []
        for file_path in files:
            url = f"https://huggingface.co/{repo_id}/resolve/{commit}/{file_path}"
            urls.append((url, file_path))

        # Ensure URLs are unique to prevent duplicate downloads
        unique_urls = []
        seen_urls = set()
        for url, path in urls:
            if url not in seen_urls:
                unique_urls.append((url, path))
                seen_urls.add(url)
        return unique_urls, commit
