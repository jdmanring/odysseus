"""Pure helpers for shaping cookbook task output for the status response.

Kept dependency-free (no FastAPI / SQLAlchemy imports) so the behavior can be
unit-tested without standing up the whole app.
"""

import re

_FETCHING_ZERO_FILES_RE = re.compile(r"Fetching\s+0\s+files", re.IGNORECASE)

# Probe scripts for the dead-session download check, run as
# `python3 -c <PROBE> <repo_id> <cache_root>` (locally or over SSH).
# cache_root is the task's custom download dir, '' for the default HF cache.
# It has to be passed explicitly: the download runner exports
# HF_HOME=<local_dir>, so that task's cache lives under <local_dir>/hub, and
# the probe process's own environment knows nothing about it.
# Both probes must understand BOTH downloaders' in-progress conventions:
# - hf CLI: partial blobs as blobs/*.incomplete (snapshot files are symlinks).
# - aria2c: the REAL filename grows directly under snapshots/<commit>/ with a
#   <file>.aria2 control file beside it until that file completes. A probe
#   that only knows .incomplete sees a populated snapshot dir mid-aria2c-run
#   and declares the model complete — the "finished at 23%" defect.
HF_CACHE_COMPLETE_PROBE = (
    "import os,sys;"
    "repo=sys.argv[1];"
    "root=os.path.expanduser(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2] else '';"
    "base=os.path.join(root,'hub') if root else (os.environ.get('HUGGINGFACE_HUB_CACHE') or os.path.join(os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface')), 'hub'));"
    "d=os.path.join(base,'models--'+repo.replace('/','--'));"
    "snap=os.path.join(d,'snapshots');"
    "ok=os.path.isdir(snap) and any(os.path.isdir(os.path.join(snap,x)) and os.listdir(os.path.join(snap,x)) for x in os.listdir(snap));"
    "inc=False;"
    "blobs=os.path.join(d,'blobs');"
    "inc=os.path.isdir(blobs) and any(x.endswith('.incomplete') for x in os.listdir(blobs));"
    "a2=os.path.isdir(snap) and any(x.endswith('.aria2') for _r,_d,fs in os.walk(snap) for x in fs);"
    "sys.exit(0 if ok and not inc and not a2 else 1)"
)

HF_CACHE_INCOMPLETE_PROBE = (
    "import os,sys;"
    "repo=sys.argv[1];"
    "root=os.path.expanduser(sys.argv[2]) if len(sys.argv)>2 and sys.argv[2] else '';"
    "base=os.path.join(root,'hub') if root else (os.environ.get('HUGGINGFACE_HUB_CACHE') or os.path.join(os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface')), 'hub'));"
    "d=os.path.join(base,'models--'+repo.replace('/','--'));"
    "blobs=os.path.join(d,'blobs');"
    "inc=os.path.isdir(blobs) and any(x.endswith('.incomplete') for x in os.listdir(blobs));"
    "snap=os.path.join(d,'snapshots');"
    "a2=os.path.isdir(snap) and any(x.endswith('.aria2') for _r,_d,fs in os.walk(snap) for x in fs);"
    "sys.exit(0 if inc or a2 else 1)"
)


def classify_dead_download(full_snapshot: str):
    """Resolve a dead download session's status from its runner markers.

    The runner prints DOWNLOAD_OK only after exiting 0 (and DOWNLOAD_FAILED
    otherwise), so the markers stay trustworthy after the tmux pane is gone.
    Returns (status, zero_files), or None when the snapshot carries no marker
    and the caller has to fall back to the cache probe. Same precedence as
    the live-session branch: DOWNLOAD_OK wins, except a "Fetching 0 files"
    run is an error (nothing matched the include/quant pattern).
    """
    if not full_snapshot:
        return None
    if "DOWNLOAD_OK" in full_snapshot:
        if _FETCHING_ZERO_FILES_RE.search(full_snapshot):
            return ("error", True)
        return ("completed", False)
    if "DOWNLOAD_FAILED" in full_snapshot:
        return ("error", False)
    return None


def error_aware_output_tail(full_snapshot: str, status: str) -> str:
    """Return the trailing slice of a task log for the status response.

    Failed tasks return the last 50 lines so the "Copy last 50 lines" action
    surfaces the actual error context (stack traces, build output). Running and
    other non-error tasks keep the cheaper 12-line tail to limit the payload on
    the 10s polling interval.
    """
    if not full_snapshot:
        return ""
    tail_lines = 50 if status == "error" else 12
    return "\n".join(full_snapshot.splitlines()[-tail_lines:])
