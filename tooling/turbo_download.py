import argparse
import sys
import os
from pathlib import Path
from typing import Optional

# We assume this script is run in a context where tooling.bin_manager, 
# tooling.aria2_wrapper, and tooling.hf_url_resolver are available.
# To make this work on remote hosts, we'll ensure the tooling folder is scp-ed.
try:
    from tooling.bin_manager import BinManager
    from tooling.aria2_wrapper import Aria2Wrapper
    from tooling.hf_url_resolver import HfUrlResolver
except ImportError:
    # Fallback for when the script is run directly from the tooling folder
    try:
        from bin_manager import BinManager
        from aria2_wrapper import Aria2Wrapper
        from hf_url_resolver import HfUrlResolver
    except ImportError as e:
        print(f"Import error: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Turbo HF Downloader")
    parser.add_argument("--repo", required=True, help="HF repo id")
    parser.add_argument("--token", help="HF token")
    parser.add_argument("--local-dir", help="Local directory to download into")
    parser.add_argument("--include", help="Include pattern")
    parser.add_argument("--platform", default="linux", help="Platform (linux, windows, etc.)")
    
    args = parser.parse_args()

    # 1. Ensure aria2c is present
    print(f"[*] Ensuring aria2c is installed...")
    binary_path = BinManager.ensure_binary("aria2c")
    if not binary_path:
        print("[!] Failed to install aria2c. Falling back to standard download or exiting.")
        sys.exit(1)
    print(f"[*] Using aria2c at {binary_path}")

    # 2. Resolve URLs
    print(f"[*] Resolving URLs for {args.repo}...")
    resolver = HfUrlResolver(token=args.token)
    try:
        urls = resolver.resolve_snapshot_urls(args.repo, include=args.include)
    except Exception as e:
        print(f"[!] Error resolving URLs: {e}")
        sys.exit(1)
    
    if not urls:
        print("[!] No files found matching the pattern.")
        sys.exit(0)
    
    print(f"[*] Found {len(urls)} files to download.")

    # 3. Determine base directory
    # Replicate the logic from cookbook_routes.py
    repo_short = args.repo.split("/")[-1] if "/" in args.repo else args.repo
    base_dir = Path(args.local_dir) / repo_short if args.local_dir else Path(os.environ.get("HF_HOME", "~/.cache/huggingface/hub")).expanduser() / "models" / repo_short
    base_dir.mkdir(parents=True, exist_ok=True)

    # 4. Download files
    wrapper = Aria2Wrapper(binary_path=binary_path)
    
    # We can download files in parallel by calling aria2c once with an input file,
    # or by calling it multiple times. Since aria2c is great at managing its own queue,
    # we'll create an input file.
    input_file = base_dir / "aria2_input.txt"
    with open(input_file, "w") as f:
        for url, rel_path in urls:
            # aria2c input file format:
            # URL
            #   out=filename
            f.write(f"{url}\n")
            f.write(f"  out={rel_path}\n")
    
    # We can't easily use the Aria2Wrapper for an input file directly because it's designed for single URLs.
    # Let's use a direct subprocess call for the input file.
    import subprocess
    
    cmd = [
        str(binary_path),
        "-i", str(input_file),
        "-d", str(base_dir),
        "-x", "16",
        "-s", "16",
        "-c", # Resume
    ]
    
    if args.token:
        cmd.append(f"--header=Authorization: Bearer {args.token}")
    
    print(f"[*] Starting turbo download: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        print("[*] Turbo download completed successfully!")
    except subprocess.CalledProcessError as e:
        print(f"[!] aria2c failed with exit code {e.returncode}")
        sys.exit(e.returncode)
    finally:
        if input_file.exists():
            input_file.unlink()

if __name__ == "__main__":
    main()
