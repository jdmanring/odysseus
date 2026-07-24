#!/usr/bin/env python3
"""Benchmark the memory store end to end: MemoryVectorStore against the
app-managed Qdrant server or the embedded single-writer store.

All numbers come from ONE process (embed, raw store query, and full search are
timed side by side), so decomposition is internally consistent — no comparing
figures across tools run in different processes.

Measured, per mode:
  * add()   — write-path latency (get + add per lane), p50/p95
  * search  — end-to-end memory search, p50/p95/p99/max over --n calls
  * decomposition — query embed alone, raw store query alone; the residual
    vs the full search is the adapter cost
  * concurrency (server mode only) — N worker processes each hammering
    search() concurrently; reports the combined latency distribution. The
    embedded store cannot run this by design (single-writer lock).

    python3 tooling/benchmark_memory_store.py --data-dir /build/membench \
        --mode server --port 6356
    python3 tooling/benchmark_memory_store.py --data-dir /build/membench2 \
        --mode embedded

Run each mode against a FRESH --data-dir on an idle host, twice, per the
benchmark protocol. Exit is nonzero if the process got a different store mode
than requested (e.g. server binary missing → silent embedded fallback).
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

# 30 memory-shaped documents (reused as search targets) + paraphrase queries.
DOCS = [
    f"memory-{i}: {text}" for i, text in enumerate([
        "The user's cat is named Biscuit and is afraid of thunderstorms.",
        "The user prefers writing code in a terminal-based text editor.",
        "The user drinks two cups of black coffee every morning.",
        "The user's favourite hiking trail follows a river gorge.",
        "The user plays bass guitar in a weekend cover band.",
        "The user is allergic to shellfish but not to fish.",
        "The user commutes by bicycle except when it snows.",
        "The user's home server runs a BSD operating system.",
        "The user collects vintage mechanical keyboards.",
        "The user prefers dark roast beans ground just before brewing.",
        "The user's garden grows tomatoes, basil, and hot peppers.",
        "The user watches films with subtitles even in their native language.",
        "The user keeps a paper notebook for daily task planning.",
        "The user's favourite season is autumn for the cool air.",
        "The user backs up photos to two separate external drives.",
        "The user learned to solder building amateur radio kits.",
        "The user runs five kilometres every other morning.",
        "The user's desk faces a window overlooking a maple tree.",
        "The user bakes sourdough bread most weekends.",
        "The user prefers tea in the evening to avoid caffeine.",
        "The user's first computer was a hand-me-down desktop.",
        "The user reads science fiction before falling asleep.",
        "The user keeps their code editor in a light theme by day.",
        "The user's dog walks happen at dawn and dusk.",
        "The user studied geology before switching to software.",
        "The user prefers window seats on long train rides.",
        "The user grinds their own spice blends for curries.",
        "The user swims laps at the community pool on Fridays.",
        "The user restores old film cameras as a hobby.",
        "The user keeps houseplants alive with a watering schedule.",
    ])
]
QUERIES = [
    "what is the pet called and what scares it",
    "which outdoor walking route does the user like best",
    "how does the user get to work",
    "what instrument does the user play",
    "what food can the user not eat",
    "what operating system is on the machine at home",
    "what does the user do with flour on weekends",
    "what hot drink is consumed after dark",
    "what did the user study at university",
    "which hobby involves fixing old photographic equipment",
]


def _configure_env(args) -> None:
    """Must run before ANY src.* import — constants bind DATA_DIR at import."""
    os.environ["ODYSSEUS_DATA_DIR"] = args.data_dir
    os.environ["QDRANT_PORT"] = str(args.port)
    os.environ.pop("QDRANT_HOST", None)
    os.environ.pop("EMBEDDING_URL", None)
    if args.mode == "embedded":
        os.environ["QDRANT_EMBEDDED"] = "1"
    else:
        os.environ.pop("QDRANT_EMBEDDED", None)
    os.makedirs(args.data_dir, exist_ok=True)


def _dist(lat_ms):
    lat = sorted(lat_ms)
    n = len(lat)
    return {
        "n": n,
        "p50": lat[n // 2],
        "p95": lat[min(n - 1, int(n * 0.95))],
        "p99": lat[min(n - 1, int(n * 0.99))],
        "max": lat[-1],
    }


def _fmt(d):
    return (f"p50 {d['p50']:.1f} / p95 {d['p95']:.1f} / p99 {d['p99']:.1f} / "
            f"max {d['max']:.1f} ms (n={d['n']})")


def _assert_mode(mode: str) -> str:
    from src.vector_client import get_vector_client
    client = get_vector_client()
    inner = getattr(client._q, "_client", None)
    kind = type(inner).__name__ if inner is not None else type(client._q).__name__
    is_local = "Local" in kind
    if mode == "server" and is_local:
        print(f"FAIL: requested server mode but got {kind} (server binary "
              f"missing or failed to start)", file=sys.stderr)
        raise SystemExit(1)
    if mode == "embedded" and not is_local:
        print(f"FAIL: requested embedded mode but got {kind}", file=sys.stderr)
        raise SystemExit(1)
    return kind


def worker_main(args) -> None:
    """Concurrency worker: attach to the running server, time searches.

    Startup barrier: model load takes seconds, so a worker that starts
    searching while its siblings are still loading measures startup
    interference, not steady-state contention. Print READY, then block on
    stdin for GO before timing anything."""
    _configure_env(args)
    from src.memory_vector import MemoryVectorStore
    store = MemoryVectorStore(args.data_dir)
    store.search(QUERIES[0], k=3)  # warm the full path
    print("READY", flush=True)
    if sys.stdin.readline().strip() != "GO":
        raise SystemExit(1)
    lat = []
    for i in range(args.n):
        q = QUERIES[i % len(QUERIES)]
        t = time.perf_counter()
        store.search(q, k=3)
        lat.append((time.perf_counter() - t) * 1000)
    print(json.dumps(lat))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data-dir", required=True,
                    help="FRESH dedicated data dir (never the live one)")
    ap.add_argument("--port", type=int, default=6356)
    ap.add_argument("--mode", choices=["server", "embedded"], default="server")
    ap.add_argument("--n", type=int, default=100, help="search sample count")
    ap.add_argument("--concurrency", type=int, default=4,
                    help="worker processes for the contention probe "
                         "(server mode only; 0 skips)")
    ap.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.worker:
        worker_main(args)
        return

    _configure_env(args)
    kind = _assert_mode(args.mode)
    from src.memory_vector import MemoryVectorStore
    store = MemoryVectorStore(args.data_dir)
    if not store.healthy:
        print("FAIL: store unhealthy after init", file=sys.stderr)
        raise SystemExit(1)
    if store.count() != 0:
        print(f"FAIL: store already holds {store.count()} vectors — a leftover "
              f"server on port {args.port} is serving stale data (add() would "
              f"silently skip as duplicates). Kill it and rerun with a fresh "
              f"--data-dir.", file=sys.stderr)
        raise SystemExit(1)
    print(f"Memory store benchmark: mode={args.mode} ({kind}) "
          f"data={args.data_dir}\n")

    # --- write path -------------------------------------------------------
    add_lat = []
    for i, doc in enumerate(DOCS):
        t = time.perf_counter()
        store.add(f"bench-mem-{i}", doc)
        add_lat.append((time.perf_counter() - t) * 1000)
    print(f"  add()        {_fmt(_dist(add_lat))}")

    # --- end-to-end search ------------------------------------------------
    store.search(QUERIES[0], k=3)  # warm
    e2e = []
    for i in range(args.n):
        q = QUERIES[i % len(QUERIES)]
        t = time.perf_counter()
        store.search(q, k=3)
        e2e.append((time.perf_counter() - t) * 1000)
    e2e_d = _dist(e2e)
    print(f"  search e2e   {_fmt(e2e_d)}")

    # --- decomposition (same process, same store) --------------------------
    lane = store._lanes[0]
    emb = []
    for i in range(args.n):
        q = QUERIES[i % len(QUERIES)]
        t = time.perf_counter()
        lane.encode([q], is_query=True)
        emb.append((time.perf_counter() - t) * 1000)
    emb_d = _dist(emb)
    vec = lane.encode([QUERIES[0]], is_query=True)
    raw = []
    for _ in range(args.n):
        t = time.perf_counter()
        lane.collection.query(query_embeddings=vec, n_results=3,
                              include=["distances"])
        raw.append((time.perf_counter() - t) * 1000)
    raw_d = _dist(raw)
    adapter = e2e_d["p50"] - emb_d["p50"] - raw_d["p50"]
    print(f"  ├ embed      {_fmt(emb_d)}")
    print(f"  ├ store qry  {_fmt(raw_d)}")
    print(f"  └ residual   {adapter:.1f} ms at p50 (adapter + python)")

    # --- contention probe ---------------------------------------------------
    if args.concurrency > 0 and args.mode == "server":
        per_worker = max(10, args.n // args.concurrency)
        cmd_base = [sys.executable, os.path.abspath(__file__), "--worker",
                    "--data-dir", args.data_dir, "--port", str(args.port),
                    "--mode", args.mode, "--n", str(per_worker)]
        procs = [subprocess.Popen(cmd_base, stdout=subprocess.PIPE,
                                  stdin=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
                 for _ in range(args.concurrency)]
        for p in procs:  # barrier: wait until every worker has loaded + warmed
            # App modules log to stdout; scan for the READY sentinel rather
            # than assuming it is the first line.
            for line in p.stdout:
                if line.strip() == "READY":
                    break
            else:
                print("FAIL: contention worker failed to start:\n"
                      f"{p.stderr.read()}", file=sys.stderr)
                raise SystemExit(1)
        t0 = time.perf_counter()
        for p in procs:
            p.stdin.write("GO\n")
            p.stdin.flush()
        all_lat = []
        for p in procs:
            out, _ = p.communicate(timeout=600)
            if p.returncode != 0:
                print("FAIL: contention worker died", file=sys.stderr)
                raise SystemExit(1)
            all_lat.extend(json.loads(out.strip().splitlines()[-1]))
        wall = time.perf_counter() - t0
        cd = _dist(all_lat)
        print(f"  {args.concurrency}-proc load {_fmt(cd)}  "
              f"[{len(all_lat) / wall:.0f} searches/s aggregate, "
              f"steady-state (post-barrier)]")
        print(f"    vs serial p50: {cd['p50'] / e2e_d['p50']:.2f}x  "
              f"p95: {cd['p95'] / e2e_d['p95']:.2f}x")
    elif args.concurrency > 0:
        print("  (contention probe skipped: embedded store is single-writer "
              "by design — this is the reason server mode exists)")

    if args.mode == "server":
        from src import qdrant_server
        qdrant_server.stop()
    print("\nDone. Median spread across two runs should be within noise; "
          "rerun with a fresh --data-dir.")


if __name__ == "__main__":
    main()
