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

    def resolve_snapshot_urls(self, repo_id: str, include: Optional[str] = None) -> Tuple[List[Tuple[str, str]], str]:
        """
        Returns a list of (url, relative_path) for all files in a repo snapshot.
        URLs are pinned to the current HEAD commit hash so they are reproducible.
        """
        print(f"[*] Resolving files for {repo_id} (Token: {'Yes' if self.api.token else 'No'})")
        commit = self.get_commit_hash(repo_id) or "main"

        files = []
        try:
            files = list(self.api.list_repo_files(repo_id))
            print(f"[*] HfApi found {len(files)} files.")
        except Exception as e:
            print(f"[!] HfApi failed: {e}. Trying fallback.")

        # FALLBACK: If hub library returned nothing, try the direct API tree
        if not files:
            try:
                import requests
                headers = {}
                if self.api.token:
                    headers["Authorization"] = f"Bearer {self.api.token}"
                
                resp = requests.get(f"https://huggingface.co/api/models/{repo_id}/tree/main", headers=headers, timeout=10)
                if resp.status_code == 200:
                    files = [item["path"] for item in resp.json()]
                    print(f"[*] API fallback found {len(files)} files.")
                else:
                    print(f"[!] API fallback failed: status {resp.status_code}")
            except Exception as e:
                print(f"[!] API fallback exception: {e}")

        if include:
            import fnmatch
            import os
            filtered_files = [f for f in files if fnmatch.fnmatch(f, include) or fnmatch.fnmatch(os.path.basename(f), include)]
            print(f"[*] Filtered {len(files)} files down to {len(filtered_files)} matching '{include}'")
            files = filtered_files

        urls = []
        for file_path in files:
            url = f"https://huggingface.co/{repo_id}/resolve/{commit}/{file_path}"
            urls.append((url, file_path))

        # Ensure URLs are unique
        unique_urls = []
        seen_urls = set()
        for url, path in urls:
            if url not in seen_urls:
                unique_urls.append((url, path))
                seen_urls.add(url)
        return unique_urls, commit

    def _probe_gguf_repo(self, repo_id: str) -> Optional[dict]:
        """Check if a repo actually contains GGUF files via HF metadata."""
        try:
            info = self.api.model_info(repo_id)
        except Exception:
            return None

        gguf = getattr(info, "gguf", None)
        if not gguf or not gguf.get("total"):
            return None

        siblings = getattr(info, "siblings", None) or []
        quant_files = [
            s.rfilename for s in siblings
            if hasattr(s, "rfilename") and s.rfilename.lower().endswith(".gguf")
        ]
        if not quant_files:
            return None

        return {
            "total_size": gguf["total"],
            "files": quant_files,
            "downloads": getattr(info, "downloads", 0) or 0,
        }

    def find_gguf_sources(self, base_repo_id: str) -> list:
        """Find GGUF quantizations of the given model.

        Searches HuggingFace, then probes each candidate to verify it
        actually contains GGUF files (via metadata — no download needed).
        Returns structured objects {repo, files, total_size, downloads}.
        """
        model_name = base_repo_id.split("/")[-1] if "/" in base_repo_id else base_repo_id

        try:
            models = self.api.list_models(
                search=f"{model_name} GGUF",
                sort="downloads",
                limit=15,
            )
        except Exception as e:
            import logging
            logging.error("GGUF discovery search failed for %s: %s", base_repo_id, e)
            return []

        results = []
        for m in models:
            repo_id = m.modelId
            if repo_id == base_repo_id:
                continue
            probed = self._probe_gguf_repo(repo_id)
            if probed is None:
                continue
            probed["repo"] = repo_id
            results.append(probed)

        results.sort(key=lambda r: r["downloads"], reverse=True)
        return results
