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

    def find_gguf_sources(self, base_repo_id: str) -> List[str]:
        """
        Search Hugging Face for repositories that appear to be GGUF quantizations
        of the given base_repo_id.
        """
        # Extract model name (e.g., 'Llama-3.2-11B-Vision-Instruct' from 'meta-llama/Llama-3.2-11B-Vision-Instruct')
        model_name = base_repo_id.split("/")[-1] if "/" in base_repo_id else base_repo_id

        # Search for repos containing both the model name and "GGUF"
        # We sort by downloads to find the most 'standard' quants first.
        try:
            models = self.api.list_models(
                search=f"{model_name} GGUF",
                sort="downloads",
                direction=-1,
                limit=10
            )
            # Filter for repos that actually look like GGUF sources
            # (usually have GGUF in the name or are from known quantizers)
            sources = []
            for m in models:
                repo_id = m.modelId
                # Avoid returning the base repo itself if it happens to match
                if repo_id == base_repo_id:
                    continue
                sources.append(repo_id)
            return sources
        except Exception as e:
            import logging
            logging.error(f"GGUF discovery failed for {base_repo_id}: {e}")
            return []
