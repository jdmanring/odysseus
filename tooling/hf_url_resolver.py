import fnmatch
import logging
import os
import re
import requests
from datetime import datetime, timezone
from typing import List, Tuple, Optional
from huggingface_hub import HfApi

logger = logging.getLogger(__name__)


class HfUrlResolver:
    """Resolves Hugging Face repository files to direct download URLs
    and discovers quality-scored GGUF quantizations for a given model.
    """

    def __init__(self, token: Optional[str] = None):
        # An empty string must not reach HfApi: it produces a literal
        # "Authorization: Bearer " header, which the hub rejects with
        # "Illegal header value" and knocks out the sized list_repo_tree path.
        self.api = HfApi(token=token or None)

    def find_community_quants(self, base_repo_id: str, limit: int = 5) -> list:
        """Return ungated community quantizations of base_repo_id, best first.

        Uses the hub's provenance metadata (filter=base_model:quantized:<repo>),
        not name matching — the same evidence standard as _is_quant_of. Sorted
        by downloads server-side; gated results are dropped because the whole
        point is offering repos the user can actually fetch. Returns
        [{"id", "downloads"}]; [] on any failure (this is a best-effort hint
        path and must never break the caller).
        """
        try:
            headers = {}
            if self.api.token:
                headers["Authorization"] = f"Bearer {self.api.token}"
            resp = requests.get(
                "https://huggingface.co/api/models",
                params={
                    "filter": f"base_model:quantized:{base_repo_id}",
                    "sort": "downloads",
                    "direction": "-1",
                    "limit": str(max(limit * 3, limit)),  # headroom for gated drops
                },
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            out = []
            for m in resp.json():
                if m.get("gated"):
                    continue
                out.append({"id": m.get("id", ""), "downloads": int(m.get("downloads") or 0)})
                if len(out) >= limit:
                    break
            return out
        except Exception:
            return []

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
        # Track whether ANY listing method returned an authoritative answer.
        # An empty list from a method that *succeeded* means "repo has no
        # matching files"; an empty list because every method errored (429
        # rate-limit, network) means "we never found out" — a hard failure the
        # caller must not mistake for an empty repo. See jdmanring/odysseus: a
        # rate-limited resolve returned [] and the downloader reported success.
        listing_ok = False
        listing_errors: List[str] = []

        # Primary: list_repo_tree returns sizes in a single call.
        try:
            items = list(self.api.list_repo_tree(repo_id, recursive=True))
            file_entries = [
                (item.rfilename, item.size or 0)
                for item in items
                if getattr(item, "size", None) is not None
            ]
            listing_ok = True
            logger.debug("list_repo_tree: %d files", len(file_entries))
        except Exception as e:
            listing_errors.append(f"list_repo_tree: {e}")
            logger.warning("list_repo_tree failed for %s: %s", repo_id, e)

        # Fallback 1: list_repo_files — paths only, no sizes.
        if not file_entries:
            try:
                paths = list(self.api.list_repo_files(repo_id))
                file_entries = [(p, 0) for p in paths]
                listing_ok = True
                logger.debug("list_repo_files fallback: %d files (sizes unavailable)", len(file_entries))
            except Exception as e:
                listing_errors.append(f"list_repo_files: {e}")
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
                    listing_ok = True
                    logger.debug("API tree fallback: %d files", len(file_entries))
                else:
                    listing_errors.append(f"API tree: HTTP {resp.status_code}")
                    logger.warning("API tree fallback returned %d for %s", resp.status_code, repo_id)
            except Exception as e:
                listing_errors.append(f"API tree: {e}")
                logger.warning("API tree fallback failed for %s: %s", repo_id, e)

        # Every listing method failed — this is not an empty repo, it's a failed
        # lookup (typically a 429 rate-limit when no HF token is set). Raise so
        # the caller reports a real error instead of "nothing to download".
        if not listing_ok:
            raise RuntimeError(
                f"could not list files for {repo_id}: all HuggingFace listing "
                f"methods failed ({'; '.join(listing_errors) or 'unknown error'})"
            )

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

    # ── GGUF discovery ───────────────────────────────────────────────────────

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

        likes_ratio = (likes / downloads) if downloads > 0 else 0.0
        has_evals = len(eval_results) > 0
        is_derived = len(base_models) > 0

        recency_days = None
        if last_modified:
            if isinstance(last_modified, str):
                try:
                    last_modified = datetime.fromisoformat(last_modified.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    last_modified = None
            if isinstance(last_modified, datetime):
                recency_days = (datetime.now(timezone.utc) - last_modified).days

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
            "base_models": [str(b) for b in base_models],
            "recency_days": recency_days,
        }

    # Preferred quant order for general use. When the exact requested quant
    # isn't available, the first match in this list becomes the fallback.
    _QUANT_PRIORITY = [
        "UD-Q4_K_XL",  # Unsloth Dynamic 2.0 — per-layer bit allocation, best 4-bit tier when published
        "IQ4_XS",   # imatrix Q4 — better perplexity than Q4_K_M at same or smaller size
        "IQ4_NL",   # imatrix Q4 variant
        "Q4_K_M",   # community standard; best pick when imatrix not available
        "Q5_K_M",   # higher quality, larger file
        "Q5_K_S",
        "Q4_K_S",
        "Q4_0",
        "IQ3_M",
        "Q3_K_L",
        "Q3_K_M",
        "IQ3_S",
        "UD-Q6_K_XL",  # Unsloth Dynamic 6-bit — best 6-bit tier when published
        "Q6_K_L",      # bartowski: embeddings/output at Q8_0 — beats plain Q6_K for ~2% size
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
        """Detect if a repo uses imatrix calibration from its name or author."""
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

        dl = c.get("downloads") or 0
        if dl > 0:
            score += min(40.0, 8.0 * (1 + (dl / 1000) ** 0.5))

        lr = c.get("likes_ratio") or 0.0
        score += min(10.0, lr * 20.0)

        if c.get("has_evals"):
            score += 10.0

        es = c.get("eval_score")
        if es is not None:
            if es > 1.0:
                score += min(10.0, es / 10.0)
            else:
                score += min(10.0, es * 10.0)

        tr = c.get("trending")
        if tr is not None and tr > 0:
            score += min(5.0, tr / 10.0)

        repo_id = c.get("repo", "")
        if self._detect_imatrix(repo_id):
            score += 15.0

        author = repo_id.split("/")[0] if "/" in repo_id else ""
        if author in self._REPUTED_AUTHORS:
            score += 10.0

        rd = c.get("recency_days")
        if rd is not None:
            if rd < 30:
                score += 5.0
            elif rd < 180:
                score += 3.0
            elif rd < 365:
                score += 1.0

        return score

    @staticmethod
    def _norm_model_name(name: str) -> str:
        """Collapse a model name for comparison: lowercase, alphanumerics only."""
        return re.sub(r"[^a-z0-9]", "", str(name or "").lower())

    def _is_quant_of(self, base_repo_id: str, candidate_repo_id: str,
                     candidate_base_models: list) -> bool:
        """Is the candidate repo actually a quantization of the requested model?

        HF's fuzzy search returns name-adjacent repos freely — without this
        check a request for one model can silently download a completely
        different one (a request for tiny-random/qwen3-next-moe once fetched
        an unrelated 12B "FreakStorm" merge that merely shared name tokens).

        Primary signal: the candidate's base_models metadata names the
        requested repo. Fallback for quant repos missing that metadata: the
        candidate's own repo NAME must contain the full base model name
        (normalized) — partial token overlap is not enough.
        """
        base_lower = base_repo_id.lower()
        for bm in candidate_base_models or []:
            if str(bm).lower() == base_lower:
                return True
        base_name = base_repo_id.split("/")[-1] if "/" in base_repo_id else base_repo_id
        base_norm = self._norm_model_name(base_name)
        if not base_norm:
            return False
        return base_norm in self._norm_model_name(candidate_repo_id.split("/")[-1])

    def find_gguf_sources(self, base_repo_id: str) -> list:
        """Find GGUF quantizations of the given model.

        Searches HuggingFace, probes each candidate to verify it actually
        contains GGUF files (via metadata — no download needed) AND is a
        quantization of the requested model (base_models metadata, with a
        strict name-containment fallback), scores on downloads, likes ratio,
        benchmark scores, trending, imatrix use, author reputation, and
        recency. Returns results sorted by score; empty when no candidate is
        genuinely derived from the requested model — never a substitute.
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
            if not self._is_quant_of(base_repo_id, repo_id, probed.get("base_models")):
                logger.info("GGUF discovery: rejected %s — not a quantization of %s",
                            repo_id, base_repo_id)
                continue
            probed["repo"] = repo_id
            probed["quality_score"] = self._score_candidate(probed)
            probed["preferred_file"] = self._preferred_quant_file(probed["files"])
            results.append(probed)

        results.sort(key=lambda r: r["quality_score"], reverse=True)
        return results
