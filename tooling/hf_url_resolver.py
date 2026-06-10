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

    # Known quantization format patterns — presence in a repo name is a
    # strong signal that the repo contains properly quantized GGUF files.
    _QUANT_PATTERNS = [
        "Q2_K", "Q3_K", "Q4_K", "Q5_K", "Q6_K", "Q8_0",
        "Q4_0", "Q4_1", "Q5_0", "Q5_1",
        "Q4_K_M", "Q4_K_S", "Q5_K_M", "Q5_K_S",
        "Q6_K_M", "Q6_K_S", "Q8_0_M",
        "IQ1", "IQ2", "IQ3", "IQ4",
        "IQ1_S", "IQ1_M", "IQ2_S", "IQ2_M", "IQ2_XS",
        "IQ3_S", "IQ3_M", "IQ3_XS", "IQ3_XXS",
        "IQ4_NL", "IQ4_XS",
        "F16", "BF16",
    ]

    def _score_gguf_repo(self, repo_id: str, model_name: str) -> int:
        """Score a candidate GGUF repo by quality signals.

        Higher score = better candidate.  Signals:
        - +100  repo name contains a recognized quantization format
        - +50   repo name contains "GGUF" explicitly
        - +25   repo name contains the exact model name
        - +10   repo owner matches the base model's owner (official quant)
        """
        score = 0
        repo_lower = repo_id.lower()
        repo_owner = repo_id.split("/")[0] if "/" in repo_id else ""
        base_owner = model_name.split("/")[0] if "/" in model_name else ""

        for pat in self._QUANT_PATTERNS:
            if pat.lower() in repo_lower:
                score += 100
                break

        if "gguf" in repo_lower:
            score += 50

        base_model = model_name.lower().split("/")[-1]
        if base_model in repo_lower:
            score += 25

        if repo_owner and repo_owner == base_owner:
            score += 10

        return score

    def find_gguf_sources(self, base_repo_id: str) -> List[str]:
        """Search HuggingFace for GGUF quantizations of the given model.

        Returns repos ranked by quality score (quantization format match,
        explicit GGUF naming, model name match, same-owner bonus) and
        then by downloads within each tier.
        """
        model_name = base_repo_id.split("/")[-1] if "/" in base_repo_id else base_repo_id

        try:
            models = self.api.list_models(
                search=f"{model_name} GGUF",
                sort="downloads",
                direction=-1,
                limit=20,
            )
        except Exception as e:
            import logging
            logging.error("GGUF discovery search failed for %s: %s", base_repo_id, e)
            return []

        scored = []
        for m in models:
            repo_id = m.modelId
            if repo_id == base_repo_id:
                continue
            s = self._score_gguf_repo(repo_id, model_name)
            downloads = getattr(m, "downloads", None) or 0
            scored.append((s, downloads, repo_id))

        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        min_score = 50
        return [repo_id for score, _, repo_id in scored if score >= min_score]
