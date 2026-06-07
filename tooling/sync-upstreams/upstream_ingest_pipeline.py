#!/usr/bin/env python3
"""
Upstream Ingest Pipeline — Odysseus fork
Propagates changes from upstream-mirror to integration through a
verification pipeline: Sync → Gate(Syntax/Lint/Tests) → Promote.

Usage:
    python3 tooling/sync-upstreams/upstream_ingest_pipeline.py                        # full sync
    python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --dry-run              # gates only
    python3 tooling/sync-upstreams/upstream_ingest_pipeline.py --skip-tests           # sync, skip pytest (CI mode)
"""

import argparse
import logging
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, stream=sys.stdout)
logger = logging.getLogger("upstream_ingest_pipeline")

REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
INTEGRATION_BRANCH = "integration"
MIRROR_BRANCH = "upstream-mirror"
UPSTREAM_BRANCH = "dev"          # pewdiepie-archdaemon/odysseus default branch
REQUIRED_REMOTES = {"upstream", "origin"}

# Files owned by this fork that must not be overwritten by upstream merges.
# After each merge the pipeline restores these to their integration-branch state.
# Extend this list as you add fork-specific patches.
PROTECTED_FILES: list[str] = [
    "tooling/sync-upstreams/upstream_ingest_pipeline.py",
    ".github/workflows/sync-upstream.yml",
    ".env.example",               # may diverge if we add fork-specific env vars
    "README.md",                  # assets/ paths diverge from upstream's docs/ paths
]

# Media file extensions that were moved from docs/ to assets/.
# If upstream re-adds these to docs/ during a merge, the post-merge cleanup removes them.
_MOVED_TO_ASSETS_EXTS = {".gif", ".webm", ".jpg", ".jpeg", ".png", ".svg", ".webp"}


class Colors:
    BLUE = "\033[0;34m"
    GREEN = "\033[0;32m"
    RED = "\033[0;31m"
    YELLOW = "\033[0;33m"
    NC = "\033[0m"


def log_info(msg: str) -> None:
    print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")


def log_success(msg: str) -> None:
    print(f"{Colors.GREEN}[OK]{Colors.NC} {msg}")


def log_warn(msg: str) -> None:
    print(f"{Colors.YELLOW}[WARN]{Colors.NC} {msg}", file=sys.stderr)


def log_error(msg: str) -> None:
    print(f"{Colors.RED}[FAIL]{Colors.NC} {msg}", file=sys.stderr)


def _resolve_python() -> str:
    venv_python = REPO_ROOT / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _resolve_pytest() -> list[str]:
    venv_pytest = REPO_ROOT / "venv" / "bin" / "pytest"
    if venv_pytest.exists():
        return [str(venv_pytest)]
    system_pytest = shutil.which("pytest")
    if system_pytest:
        return [system_pytest]
    raise RuntimeError(
        "pytest not found. Activate the venv or install it: venv/bin/pip install pytest"
    )


def _resolve_ruff() -> list[str] | None:
    """Returns ruff command list, or None if ruff is not available (lint gate skipped)."""
    venv_ruff = REPO_ROOT / "venv" / "bin" / "ruff"
    if venv_ruff.exists():
        return [str(venv_ruff)]
    system_ruff = shutil.which("ruff")
    if system_ruff:
        return [system_ruff]
    env_ruff = os.environ.get("RUFF_BIN")
    if env_ruff:
        if not Path(env_ruff).exists():
            raise RuntimeError(f"RUFF_BIN={env_ruff!r} does not exist.")
        return [env_ruff]
    return None


@dataclass
class SyncResult:
    success: bool
    stage: str
    message: str
    lkg_tag: str | None = None
    dry_run: bool = False


class _GitRunner:
    def __init__(self, root: Path) -> None:
        self.root = root

    def run(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(cmd, cwd=self.root, capture_output=True, text=True, check=check)

    def output(self, cmd: list[str]) -> str:
        return self.run(cmd).stdout.strip()

    def current_branch(self) -> str:
        return self.output(["git", "rev-parse", "--abbrev-ref", "HEAD"])


class PreFlight:
    def __init__(self, git: _GitRunner) -> None:
        self._git = git

    def check(self) -> bool:
        logger.info("Running pre-flight checks...")
        try:
            branch = self._git.current_branch()
            if branch != INTEGRATION_BRANCH:
                raise RuntimeError(f"Must be on '{INTEGRATION_BRANCH}' branch. Current: '{branch}'")

            remotes = set(self._git.output(["git", "remote"]).splitlines())
            missing = REQUIRED_REMOTES - remotes
            if missing:
                raise RuntimeError(f"Missing required remotes: {missing}")

            dirty = self._git.run(["git", "diff", "--quiet", "HEAD"], check=False).returncode != 0
            if dirty:
                raise RuntimeError(
                    "Integration branch has uncommitted changes — stash or commit before syncing."
                )

            venv = REPO_ROOT / "venv"
            if not venv.exists():
                raise RuntimeError(
                    "venv not found. Create it: python3 -m venv venv && venv/bin/pip install -r requirements.txt"
                )

            log_success("Pre-flight passed.")
            return True
        except (RuntimeError, subprocess.CalledProcessError, OSError) as e:
            log_error(f"Pre-flight failed: {e}")
            return False


class SyncManager:
    def __init__(self, git: _GitRunner) -> None:
        self._git = git
        self.staging_branch: str | None = None

    def sync_mirror(self) -> bool:
        log_info(f"Fetching upstream/{UPSTREAM_BRANCH}...")
        self._git.run(["git", "fetch", "upstream", UPSTREAM_BRANCH])

        new_count = self._git.output(
            ["git", "rev-list", "--count", f"upstream/{UPSTREAM_BRANCH}", f"^{INTEGRATION_BRANCH}"]
        )
        if new_count == "0":
            log_success("Already up to date — nothing to sync.")
            return False

        log_info(f"{new_count} new upstream commit(s) to integrate.")
        log_info(f"Resetting {MIRROR_BRANCH} to upstream/{UPSTREAM_BRANCH}...")
        self._git.run(["git", "checkout", "-f", MIRROR_BRANCH])
        self._git.run(["git", "reset", "--hard", f"upstream/{UPSTREAM_BRANCH}"])
        self._git.run(["git", "checkout", INTEGRATION_BRANCH])
        log_success("Mirror synchronized.")
        return True

    def create_staging(self) -> None:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        self.staging_branch = f"sync/staging-{timestamp}"
        log_info(f"Creating staging branch: {self.staging_branch}")
        self._git.run(["git", "checkout", "-b", self.staging_branch])

    def merge_mirror_to_stage(self) -> None:
        integration_ref = self._git.output(["git", "rev-parse", "HEAD"])
        log_info(f"Merging {MIRROR_BRANCH} into {self.staging_branch}...")
        result = self._git.run(["git", "merge", MIRROR_BRANCH, "--no-edit"], check=False)
        if result.returncode == 0:
            log_success("Merge clean.")
            self._restore_protected_files(integration_ref)
            return

        conflict_files = self._git.output(["git", "diff", "--name-only", "--diff-filter=U"])
        self._git.run(["git", "merge", "--abort"], check=False)
        raise RuntimeError(
            f"Merge conflict — manual resolution required:\n{conflict_files}\n\n"
            "Resolve, commit, then re-run the ingest pipeline."
        )

    def _restore_protected_files(self, integration_ref: str) -> None:
        for path in PROTECTED_FILES:
            self._git.run(["git", "checkout", integration_ref, "--", path], check=False)

        # Remove any media files upstream re-added to docs/ that we moved to assets/.
        # Upstream has these in docs/; our fork moved them to assets/. If the merge
        # re-adds them to docs/, remove the docs/ copy so assets/ stays canonical.
        docs_dir = REPO_ROOT / "docs"
        assets_dir = REPO_ROOT / "assets"
        removed_docs_media = []
        if docs_dir.exists() and assets_dir.exists():
            for f in docs_dir.iterdir():
                if f.suffix.lower() in _MOVED_TO_ASSETS_EXTS and (assets_dir / f.name).exists():
                    self._git.run(["git", "rm", "-f", "--ignore-unmatch", str(f.relative_to(REPO_ROOT))], check=False)
                    removed_docs_media.append(f.name)
        if removed_docs_media:
            log_info(f"Removed {len(removed_docs_media)} docs/ media file(s) re-added by upstream (canonical copies in assets/): {removed_docs_media}")

        staged = self._git.output(["git", "diff", "--cached", "--name-only"])
        restored = [f for f in staged.splitlines() if f in PROTECTED_FILES or f.startswith("docs/")]
        if restored:
            log_info(f"Restored/cleaned {len(restored)} fork-diverged file(s).")
            self._git.run(
                ["git", "commit", "-m", "chore(sync): restore fork-owned files after upstream merge"]
            )
        else:
            log_success("Protected files unchanged by upstream — no restoration needed.")

    def cleanup_staging(self) -> None:
        if not self.staging_branch:
            return
        if self._git.current_branch() == self.staging_branch:
            self._git.run(["git", "checkout", INTEGRATION_BRANCH])
        self._git.run(["git", "branch", "-D", self.staging_branch], check=False)
        self.staging_branch = None


class GateKeeper:
    def __init__(self, git: _GitRunner, skip_tests: bool = False) -> None:
        self._git = git
        self._python = _resolve_python()
        self._ruff = _resolve_ruff()
        self._skip_tests = skip_tests

    def verify(self) -> bool:
        return self._gate_syntax() and self._gate_lint() and self._gate_tests()

    def _gate_syntax(self) -> bool:
        logger.info("Gate 1/3: Python syntax check (app.py + core modules)...")
        targets = ["app.py", "core", "src", "routes", "services"]
        errors = []
        for target in targets:
            p = REPO_ROOT / target
            if not p.exists():
                continue
            if p.is_file():
                files = [p]
            else:
                files = list(p.rglob("*.py"))
            for f in files:
                result = subprocess.run(
                    [self._python, "-m", "py_compile", str(f)],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    errors.append(f"{f.relative_to(REPO_ROOT)}: {result.stderr.strip()}")
        if errors:
            log_error("Syntax gate failed:\n" + "\n".join(errors))
            return False
        log_success("Syntax gate passed.")
        return True

    def _gate_lint(self) -> bool:
        if self._ruff is None:
            log_warn("Gate 2/3: ruff not found — lint gate skipped. Install: venv/bin/pip install ruff")
            return True
        logger.info("Gate 2/3: Ruff lint (warn-only — upstream style is not our concern)...")
        result = subprocess.run(
            self._ruff + ["check", "."],
            cwd=REPO_ROOT,
            capture_output=True,
        )
        if result.returncode != 0:
            log_warn("Lint warnings present in upstream code — not blocking sync.")
        else:
            log_success("Lint gate passed.")
        return True

    def _gate_tests(self) -> bool:
        if self._skip_tests:
            log_warn("Gate 3/3: Pytest skipped (--skip-tests / CI mode).")
            return True
        logger.info("Gate 3/3: Pytest smoke tests...")
        try:
            pytest_cmd = _resolve_pytest()
        except RuntimeError as e:
            log_warn(f"Gate 3/3: {e} — test gate skipped.")
            return True
        result = subprocess.run(
            pytest_cmd + ["tests/", "-x", "-q", "--tb=short", "--timeout=60"],
            cwd=REPO_ROOT,
        )
        if result.returncode != 0:
            log_error("Test gate failed.")
            return False
        log_success("Test gate passed.")
        return True


class PromotionEngine:
    def __init__(self, git: _GitRunner) -> None:
        self._git = git

    def promote(self, staging_branch: str) -> str:
        log_info(f"Promoting {staging_branch} → {INTEGRATION_BRANCH}...")
        self._git.run(["git", "checkout", INTEGRATION_BRANCH])
        self._git.run(["git", "merge", "--ff-only", staging_branch])

        timestamp = datetime.now().strftime("%Y%m%d-%H%M")
        tag = f"LKG-{timestamp}"
        self._git.run(["git", "tag", "-a", tag, "-m", f"Last Known Good — {timestamp}"])
        log_success(f"Tagged as {tag}.")
        return tag


class UpstreamIngestPipeline:
    """
    upstream/dev
        ↓  (fetch + reset)
    upstream-mirror
        ↓  (merge into staging branch off integration)
    sync/staging-TIMESTAMP
        ↓  (Gate 1: Python syntax check)
        ↓  (Gate 2: ruff lint — skipped if ruff absent)
        ↓  (Gate 3: pytest smoke tests)
    integration  [ff-only merge + LKG tag]
    """

    def __init__(self, dry_run: bool = False, skip_tests: bool = False, push: bool = False) -> None:
        self._git = _GitRunner(REPO_ROOT)
        self._dry_run = dry_run
        self._push = push
        self.preflight = PreFlight(self._git)
        self.sync = SyncManager(self._git)
        self.gates = GateKeeper(self._git, skip_tests=skip_tests)
        self.promotion = PromotionEngine(self._git)

    def run(self) -> SyncResult:
        if self._dry_run:
            log_warn("DRY RUN — gates will run against current state; no commits or tags.")

        if not self.preflight.check():
            return SyncResult(False, "PREFLIGHT", "Pre-flight checks failed.")

        try:
            if not self._dry_run:
                has_new = self.sync.sync_mirror()
                if not has_new:
                    return SyncResult(True, "UP_TO_DATE", "Already up to date.")
                self.sync.create_staging()
                self.sync.merge_mirror_to_stage()
            else:
                log_info("[dry-run] Skipping sync and staging.")

            if not self.gates.verify():
                return SyncResult(
                    False,
                    "VERIFICATION",
                    "One or more verification gates failed.",
                    dry_run=self._dry_run,
                )

            if self._dry_run:
                log_success("[dry-run] All gates passed. Nothing promoted.")
                return SyncResult(True, "DRY_RUN", "Dry run complete.", dry_run=True)

            if not self.sync.staging_branch:
                raise RuntimeError("staging_branch is None after create_staging — this is a bug")
            tag = self.promotion.promote(self.sync.staging_branch)
            if self._push:
                log_info("Pushing integration, upstream-mirror, and tags to origin...")
                self._git.run(["git", "push", "origin", INTEGRATION_BRANCH])
                self._git.run(["git", "push", "origin", MIRROR_BRANCH])
                self._git.run(["git", "push", "origin", "--tags"])
                log_success("Pushed.")
            else:
                log_warn("Not pushing — run with --push or push manually: git push origin integration upstream-mirror --follow-tags")
            return SyncResult(True, "PROMOTION", "Sync complete.", lkg_tag=tag)

        except (RuntimeError, subprocess.CalledProcessError, OSError) as e:
            log_error(str(e))
            return SyncResult(False, "PIPELINE_ERROR", str(e))
        finally:
            if not self._dry_run:
                self.sync.cleanup_staging()
                if self._git.current_branch() != INTEGRATION_BRANCH:
                    self._git.run(["git", "checkout", INTEGRATION_BRANCH], check=False)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upstream Ingest Pipeline — ingests upstream/dev into integration."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all gates against current state without syncing or promoting.",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip the pytest gate. Used in CI where installing test deps is impractical.",
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push integration, upstream-mirror, and tags to origin after promotion.",
    )
    args = parser.parse_args()

    orch = UpstreamIngestPipeline(dry_run=args.dry_run, skip_tests=args.skip_tests, push=args.push)
    result = orch.run()

    if result.success:
        if result.lkg_tag:
            log_success(f"Pipeline complete. LKG tag: {result.lkg_tag}")
        elif result.stage == "UP_TO_DATE":
            log_success("Nothing to do — integration is already current.")
        sys.exit(0)
    else:
        log_error(f"Pipeline failed at [{result.stage}]: {result.message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
