import os
import logging
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from huggingface_hub import HfApi

logger = logging.getLogger(__name__)

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
        """Check if a repo actually contains GGUF files via HF metadata.

        Uses expand= to fetch quality signals in a single call:
        downloads, likes, trending, eval results, base models, and
        last-modified date. These feed the quality score.
        """
        try:
            info = self.api.model_info(
                repo_id,
                expand=[
                    "trendingScore", "evalResults", "baseModels",
                    "downloadsAllTime", "gguf", "siblings",
                    "downloads", "likes", "lastModified",
                ],
            )
        except Exception:
            return None

        gguf = getattr(info, "gguf", None)
        if not gguf or not gguf.get("total"):
            return None

        siblings = getattr(info, "siblings", None) or []
        quant_files = [
            s.rfilename for s in siblings
            if hasattr(s, "rfilename")
            and s.rfilename.lower().endswith(".gguf")
            and "mmproj" not in s.rfilename.lower()
        ]
        if not quant_files:
            return None

        downloads = getattr(info, "downloads", 0) or 0
        likes = getattr(info, "likes", 0) or 0
        trending = getattr(info, "trending_score", None)
        eval_results = getattr(info, "eval_results", None) or []
        base_models = getattr(info, "base_models", None) or []
        last_modified = getattr(info, "last_modified", None)
        author = getattr(info, "author", None)

        # Derived signals
        likes_ratio = (likes / downloads) if downloads > 0 else 0.0
        has_evals = len(eval_results) > 0
        is_derived = len(base_models) > 0

        # Recency: days since last commit (lower is better)
        recency_days = None
        if last_modified:
            if isinstance(last_modified, str):
                try:
                    last_modified = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    last_modified = None
            if isinstance(last_modified, datetime):
                recency_days = (datetime.now(timezone.utc) - last_modified).days

        # Best eval score (normalized to 0..1 if possible)
        eval_score = None
        for ev in eval_results:
            val = getattr(ev, "value", None)
            if val is not None:
                try:
                    v = float(val)
                    if eval_score is None or v > eval_score:
                        eval_score = v
                except (TypeError, ValueError):
                    pass

        return {
            "total_size": gguf["total"],
            "files": quant_files,
            "downloads": downloads,
            "likes": likes,
            "likes_ratio": likes_ratio,
            "trending": trending,
            "has_evals": has_evals,
            "eval_score": eval_score,
            "is_derived": is_derived,
            "recency_days": recency_days,
            "author": author,
        }

    # Preferred quant order for general use. When model.quant doesn't exist in
    # a discovered repo (e.g. a Q4_K_M request hitting an imatrix-only repo),
    # the first match in this list becomes the fallback include pattern.
    _QUANT_PRIORITY = [
        "Q4_K_M",   # community standard recommendation
        "IQ4_XS",   # imatrix equivalent to Q4_K_M
        "IQ4_NL",   # imatrix Q4 variant
        "Q5_K_M",   # higher quality
        "Q5_K_S",
        "Q4_K_S",
        "Q4_0",
        "Q3_K_L",
        "Q3_K_M",
        "IQ3_M",
        "IQ3_S",
        "Q6_K",
        "Q8_0",
        "IQ2_M",
        "Q2_K",
    ]

    @classmethod
    def _preferred_quant_file(cls, files: list) -> Optional[str]:
        """Pick the best file from a list by quant preference order."""
        for quant in cls._QUANT_PRIORITY:
            for f in files:
                if quant.lower() in os.path.basename(f).lower():
                    return f
        return files[0] if files else None

    _REPUTED_AUTHORS = {
        # S-tier: uses imatrix calibration, maintains recommended collections,
        # writes technical comparisons. Top choice.
        "bartowski",
        # S-tier: most prolific and well-known, huge catalog, reliable quality.
        "TheBloke",
        # A-tier: most prolific overall, uses imatrix I1/I2 presets.
        "mradermacher",
        # A-tier: very high download counts, dedicated GGUF collection.
        "MaziyarPanahi",
        # A-tier: high volume, broad coverage, community-referenced.
        "tensorblock",
        # B-tier: all models use imatrix, consistent quality.
        "legraphista",
        "duyntnet",
        # B-tier: solid quality, detailed model cards.
        "second-state",
    }

    _IMATRIX_AUTHORS = {"bartowski", "duyntnet", "mradermacher"}

    @classmethod
    def _detect_imatrix(cls, repo_id: str) -> bool:
        """Detect if a repo uses imatrix calibration from its name."""
        repo_lower = repo_id.lower()
        author = repo_id.split("/")[0] if "/" in repo_id else ""
        if author in cls._IMATRIX_AUTHORS:
            return True
        return "imatrix" in repo_lower or "imat" in repo_lower

    def _score_candidate(self, c: dict) -> float:
        """Score a probed GGUF repo for quality.

        Signals and their rationale:
        - downloads (0-40): strongest signal of community trust
        - likes_ratio (0-10): engagement quality — high ratio = strong approval
        - has_evals (0-10): benchmark scores exist = well-tested
        - eval_score (0-10): if benchmarks exist, higher is better
        - trending (0-5): recent momentum on HF
        - imatrix (0-15): importance matrix calibration = better quality at same bit width
        - author reputation (0-10): known high-quality quantizer
        - recency (0-5): recently updated = actively maintained (capped low — old imatrix > new basic)
        """
        score = 0.0

        # Downloads: log-scale so a repo with 10x downloads doesn't dominate
        dl = c.get("downloads") or 0
        if dl > 0:
            score += min(40.0, 8.0 * (1 + (dl / 1000) ** 0.5))

        # Likes ratio: high ratio = strong community approval
        lr = c.get("likes_ratio") or 0.0
        score += min(10.0, lr * 20.0)

        # Has benchmark scores = well-tested
        if c.get("has_evals"):
            score += 10.0

        # Best eval score: normalize if it looks like a percentage (0-100)
        es = c.get("eval_score")
        if es is not None:
            if es > 1.0:
                score += min(10.0, es / 10.0)
            else:
                score += min(10.0, es * 10.0)

        # Trending: HF's internal trending score
        tr = c.get("trending")
        if tr is not None and tr > 0:
            score += min(5.0, tr / 10.0)

        # Importance matrix calibration = measurably better quantization quality.
        # This is the single strongest quality signal after downloads.
        repo_id = c.get("repo", "")
        if self._detect_imatrix(repo_id):
            score += 15.0

        # Author reputation: known high-quality quantizers
        author = repo_id.split("/")[0] if "/" in repo_id else ""
        if author in self._REPUTED_AUTHORS:
            score += 10.0

        # Recency: small bonus for recently updated, but old imatrix from a
        # good author beats new basic quant from an unknown one.
        rd = c.get("recency_days")
        if rd is not None:
            if rd < 30:
                score += 5.0
            elif rd < 180:
                score += 3.0
            elif rd < 365:
                score += 1.0

        return score

    def find_gguf_sources(self, base_repo_id: str) -> list:
        """Find GGUF quantizations of the given model.

        Searches HuggingFace, then probes each candidate to verify it
        actually contains GGUF files (via metadata — no download needed).
        Scores candidates on downloads, likes ratio, benchmark scores,
        trending, recency, and whether it's a direct source vs derived.
        Returns structured objects sorted by score descending.
        """
        model_name = base_repo_id.split("/")[-1] if "/" in base_repo_id else base_repo_id

        try:
            models = self.api.list_models(
                search=f"{model_name} GGUF",
                sort="downloads",
                limit=15,
            )
        except Exception as e:
            logger.error("GGUF discovery search failed for %s: %s", base_repo_id, e)
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
            probed["quality_score"] = self._score_candidate(probed)
            probed["preferred_file"] = self._preferred_quant_file(probed["files"])
            results.append(probed)

        results.sort(key=lambda r: r["quality_score"], reverse=True)
        return results
