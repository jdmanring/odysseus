"""Behavioral tests for the cache-shape probes that decide download completion.

The complete-probe only knew the hf CLI's blobs/*.incomplete convention;
aria2c grows the REAL filename under snapshots/ with a <file>.aria2 control
file beside it, so mid-aria2c-download the probe saw a populated snapshot dir,
found no .incomplete blobs, and declared the model complete — the recorded
"card says finished at 23%" defect. These tests run the actual probe strings
as subprocesses against synthetic cache trees.
"""
import subprocess
import sys

from routes.cookbook_output import HF_CACHE_COMPLETE_PROBE, HF_CACHE_INCOMPLETE_PROBE

REPO = "org/model"


def _mk_cache(tmp_path, files, blobs=()):
    snap = tmp_path / "hub" / "models--org--model" / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    for name in files:
        (snap / name).write_bytes(b"x")
    if blobs:
        bdir = tmp_path / "hub" / "models--org--model" / "blobs"
        bdir.mkdir(parents=True)
        for name in blobs:
            (bdir / name).write_bytes(b"x")
    return tmp_path


def _run(probe, root):
    return subprocess.run(
        [sys.executable, "-c", probe, REPO, str(root)], timeout=15
    ).returncode


def test_complete_probe_rejects_mid_aria2c_download(tmp_path):
    root = _mk_cache(tmp_path, ["model.safetensors", "model.safetensors.aria2"])
    assert _run(HF_CACHE_COMPLETE_PROBE, root) != 0, \
        ".aria2 control file present = download in progress, NEVER complete"


def test_complete_probe_accepts_finished_aria2c_download(tmp_path):
    root = _mk_cache(tmp_path, ["config.json", "model.safetensors"])
    assert _run(HF_CACHE_COMPLETE_PROBE, root) == 0


def test_complete_probe_rejects_hf_incomplete_blobs(tmp_path):
    root = _mk_cache(tmp_path, ["model.safetensors"], blobs=["deadbeef.incomplete"])
    assert _run(HF_CACHE_COMPLETE_PROBE, root) != 0


def test_incomplete_probe_sees_aria2_control_files(tmp_path):
    root = _mk_cache(tmp_path, ["model.safetensors", "model.safetensors.aria2"])
    assert _run(HF_CACHE_INCOMPLETE_PROBE, root) == 0, \
        "resumable aria2c partial must read as incomplete"


def test_incomplete_probe_clean_cache_is_not_incomplete(tmp_path):
    root = _mk_cache(tmp_path, ["model.safetensors"])
    assert _run(HF_CACHE_INCOMPLETE_PROBE, root) != 0


# ── output tail sizing (routes/cookbook_output.py) ───────────────────────────

def test_download_tail_is_big_enough_for_a_multifile_summary_and_drops_url_walls():
    from routes.cookbook_output import error_aware_output_tail
    summary = "\n".join(
        [f"[#aaaa{i:02d} 1.0GiB/2.0GiB(50%) CN:2 DL:2.0MiB ETA:5m]\nFILE: /cache/model-{i}.safetensors"
         for i in range(5)]
    )
    url_wall = "\n".join(
        f"07/20 [NOTICE] Redirecting to https://cdn.example/{'A' * 2500}" for _ in range(4)
    )
    snap = summary + "\n" + url_wall
    tail = error_aware_output_tail(snap, "running", "download")
    assert "https://" not in tail, "signed-URL walls are stripped for downloads"
    for i in range(5):
        assert f"[#aaaa{i:02d}" in tail, "every per-file progress line survives"
    # non-download running tasks keep the cheap 12-line tail
    serve_tail = error_aware_output_tail("\n".join(str(i) for i in range(40)), "running", "serve")
    assert len(serve_tail.splitlines()) == 12
