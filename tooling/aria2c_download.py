import argparse
import shutil
import subprocess
import sys
import os
import tempfile
from pathlib import Path
from typing import Optional

try:
    from tooling.bin_manager import BinManager
    from tooling.hf_url_resolver import HfUrlResolver
except ImportError:
    try:
        from bin_manager import BinManager
        from hf_url_resolver import HfUrlResolver
    except ImportError as e:
        print(f"Import error: {e}")
        sys.exit(1)


def get_aria2c() -> Optional[Path]:
    """Return the aria2c binary path. Auto-installs via BinManager if missing."""
    path = BinManager.ensure_binary("aria2c")
    if path:
        return Path(path)
    system_path = shutil.which("aria2c")
    if system_path:
        return Path(system_path)
    return None


def download_file(
    aria2c: Path,
    url: str,
    out_dir: Path,
    filename: str,
    token: Optional[str],
) -> bool:
    """Download a single file. Used by tests."""
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        str(aria2c),
        "--continue=true",
        "--max-connection-per-server=16",
        "--split=16",
        "--min-split-size=1M",
        "--console-log-level=notice",
        "--summary-interval=10",
        f"--dir={out_dir}",
        f"--out={filename}",
    ]
    if token:
        cmd.append(f"--header=Authorization: Bearer {token}")
    cmd.append(url)
    result = subprocess.run(cmd)
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description="aria2c HF Downloader")
    parser.add_argument("--repo", required=True, help="HuggingFace repo id (owner/name)")
    parser.add_argument("--token", help="HuggingFace access token for gated models")
    parser.add_argument("--local-dir", help="Destination directory (default: HF cache)")
    parser.add_argument("--include", help="File glob filter (e.g. '*.safetensors')")
    args = parser.parse_args()

    # Guard: refuse to start if another download for the same repo is already
    # running. Checks by PID so stale lock files from crashed runs are ignored.
    lock_path = Path(f"/tmp/aria2c_dl_{args.repo.replace('/', '_')}.pid")
    if lock_path.exists():
        try:
            pid = int(lock_path.read_text().strip())
            os.kill(pid, 0)   # raises OSError if PID is not running
            print(f"[!] Download for {args.repo} is already running (PID {pid}). Exiting.")
            sys.exit(0)
        except (ValueError, ProcessLookupError, OSError):
            lock_path.unlink(missing_ok=True)  # stale lock
    lock_path.write_text(str(os.getpid()))
    try:
        _main(args)
    finally:
        lock_path.unlink(missing_ok=True)


def _main(args) -> None:
    # 1. Get aria2c binary
    aria2c = get_aria2c()
    if aria2c is None:
        print(
            "[!] aria2c not found and auto-install failed.\n"
            "    Install it manually: pacman -S aria2 / apt install aria2 / brew install aria2"
        )
        sys.exit(1)
    print(f"[*] Using aria2c: {aria2c}")

    # 2. Resolve HuggingFace file URLs + commit hash
    print(f"[*] Resolving file list for {args.repo}...")
    resolver = HfUrlResolver(token=args.token)
    try:
        urls, commit = resolver.resolve_snapshot_urls(args.repo, include=args.include)
    except Exception as e:
        print(f"[!] Failed to list files: {e}")
        sys.exit(1)

    if not urls:
        print("[!] No files matched — nothing to download.")
        sys.exit(0)
    print(f"[*] {len(urls)} file(s) to download.")
    if commit and commit != "main":
        print(f"[*] Commit: {commit[:12]}")

    # 3. Determine destination directory using the standard HF hub cache layout.
    # snapshot_download(repo_id) will find files here without re-downloading.
    if args.local_dir:
        base_dir = Path(args.local_dir)
    else:
        hub_cache = Path(
            os.environ.get("HUGGINGFACE_HUB_CACHE")
            or os.path.join(os.environ.get("HF_HOME", "~/.cache/huggingface"), "hub")
        ).expanduser()
        dir_name = "models--" + args.repo.replace("/", "--")
        model_root = hub_cache / dir_name
        snapshot_name = commit
        base_dir = model_root / "snapshots" / snapshot_name
        base_dir.mkdir(parents=True, exist_ok=True)
        refs_dir = model_root / "refs"
        refs_dir.mkdir(exist_ok=True)
        (refs_dir / "main").write_text(snapshot_name)
    base_dir.mkdir(parents=True, exist_ok=True)
    print(f"[*] Saving to: {base_dir}")

    # 4. Download all files in parallel via a single aria2c invocation.
    #
    # All URLs go into an input file. aria2c reads it, downloads up to
    # max_concurrent files simultaneously, and exits with code 0 when ALL
    # files are complete. It is a one-shot subprocess — not a daemon, no RPC.
    max_concurrent = 4   # files in parallel
    conn_per_file  = 16  # connections per file — 4×16 = 64 total

    # Create any subdirectories that appear in relative paths
    for _, rel_path in urls:
        (base_dir / rel_path).parent.mkdir(parents=True, exist_ok=True)

    parallel_count = min(max_concurrent, len(urls))
    print(f"[*] Downloading {len(urls)} file(s) ({parallel_count} in parallel)...")

    input_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.txt', prefix='aria2c_input_', delete=False
        ) as f:
            for url, rel_path in urls:
                f.write(f"{url}\n")
                f.write(f"  out={rel_path}\n")
                if args.token:
                    f.write(f"  header=Authorization: Bearer {args.token}\n")
                f.write("\n")
            input_path = Path(f.name)

        cmd = [
            str(aria2c),
            "--continue=true",
            f"--max-concurrent-downloads={max_concurrent}",
            f"--max-connection-per-server={conn_per_file}",
            f"--split={conn_per_file}",
            "--min-split-size=1M",
            "--file-allocation=none",
            "--disk-cache=64M",
            "--console-log-level=notice",
            "--summary-interval=3",
            f"--dir={base_dir}",
            f"--input-file={input_path}",
        ]
        result = subprocess.run(cmd)
    finally:
        if input_path and input_path.exists():
            input_path.unlink()

    if result.returncode != 0:
        print(f"\n[!] Download failed (aria2c exit {result.returncode}).")
        sys.exit(1)

    print(f"\n[*] Download complete. Model cached at: {base_dir}")


if __name__ == "__main__":
    main()
