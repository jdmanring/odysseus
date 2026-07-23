# Runbook: Building the Qdrant server from source on OpenBSD

**Status:** VERIFIED WORKING, including full-stack integration. Built (qdrant 1.18.3)
and installed on the OpenBSD 7.9 workbench VM (`ssh openbsd`, x86_64). End-to-end API
confirmed live: `/readyz` 200, create collection, upsert points, and vector search all
succeed. Reproducible via `tooling/bsd/build_qdrant_openbsd.sh`.

**Integration verified (2026-07-23):** `tooling/verify_memory_integration.py` passed
all four phases on the VM. It drives the real app modules (`get_vector_client`,
`MemoryVectorStore`, llama.cpp Q8_0 embeddings), no mocks. The phases:

- A: server mode asserted (`QdrantRemote`, not the embedded fallback).
- B: semantic write/search. A paraphrase query with no term overlap retrieved the
  target memory (score 0.6903).
- C: a second OS process wrote and searched the same server and collection while
  the first client stayed open. This is the app+MCP lock collision that embedded
  mode fails; against the server it just works.
- D: both processes' writes survived a full server stop/restart.

Embedding performance on the VM (idle, load 0.25, 12 vCPU / 16 GB, 2026-07-23),
via `tooling/benchmark_embedding_backends.py`: llama.cpp Q8_0 per-item p50 9.2 ms,
bulk 116 docs/s, top-1 0.917 / top-3 1.000 — the same accuracy as the Linux host
and a modest virtualization tax on its ~7 ms. Latency is flat across
`LLAMACPP_EMBED_THREADS` 2/4/8, so the defaults stand. fastembed is not comparable
here: onnxruntime does not exist on OpenBSD, which is the reason the stack unified
on llama.cpp.

Run it after any rebuild:

```sh
ssh openbsd 'cd ~/odysseus && venv/bin/python tooling/verify_memory_integration.py \
    --data-dir /build/memtest --port 6355'
```

(Dedicated port 6355 and data dir keep it clear of the live app on 7000 and any
qdrant on 6333; /build is real FFS, satisfying Qdrant's filesystem check. The
verifier stops the server it launched, and fails phase D if a leftover instance
owns the port: kill the leftover and rerun.)

Note: point the server's storage at a real FFS partition, not `/tmp` (mfs) — Qdrant
warns "Unrecognized filesystem - cannot guarantee data safety" on unknown FS types.

**Port map (no overlap):** the Odysseus app listens on **7000** (`APP_PORT`); Qdrant
uses **6333** HTTP / **6334** gRPC (`QDRANT_PORT` default 6333, per `src/vector_client.py`).
`src/qdrant_server.py` launches Qdrant on that 6333 — it never touches 7000. Smoke-test
against 6333 (or another free port), **never 7000**: binding a test Qdrant on 7000 hits
the running app instead and every request 302-redirects.

## Why source-build at all

Odysseus's memory/RAG stack wants a concurrent Qdrant **server** (`src/qdrant_server.py`),
not the single-writer embedded store — the app and the memory MCP subprocess both open
the store, and embedded mode's exclusive lock makes them collide. Platforms with an
official Qdrant binary get it from `tooling/bin_manager.py`. **OpenBSD has no official
Qdrant binary and Qdrant does not target OpenBSD**, so it must be built from source. This
matters most on OpenBSD precisely because it's a server OS — the likely deployment is a
multi-client remote server, exactly where the concurrent store is required.

There is no alternative: embedded/local mode is not acceptable for the multi-client
server case, and there is no cross-platform binary to download.

## Research first — this is a *known* porting profile, not novel territory

Every wall below is a documented OpenBSD large-Rust-project issue. Read these **before**
building, not after hitting each one (the mistake made the first time through — six
reactive rebuild cycles instead of one informed pass):

- [rustc OpenBSD platform-support](https://doc.rust-lang.org/rustc/platform-support/openbsd.html)
  — Tier-3 target; native toolchain; system allocator.
- OpenBSD disables jemalloc project-wide (system allocator is preferred/ more reliable);
  Rust upstream has repeatedly disabled jemalloc per-arch for the same reasons.
- "On OpenBSD, build failures are mostly **undefined symbols in libc**" — the `mincore`
  class. OpenBSD removed `mincore(2)`.
- The truly native path is an **OpenBSD port** using the `MODCARGO` ports framework
  (handles Rust conventions, allocator, and patches). qdrant is not in ports, so we
  hand-build — but the ports framework is the mechanism to prefer if this is ever
  upstreamed to ports.

## The walls and their fixes

All source fixes are in `tooling/bsd/patch_qdrant_openbsd.py` (idempotent, behaviour-
preserving); build-environment fixes are in `tooling/bsd/build_qdrant_openbsd.sh`.

| # | Wall | Symptom | Fix |
|---|------|---------|-----|
| 1 | Nightly std features in `common`/`segment` (`as_ref_unchecked`, `cfg_select!`, if-let match guards) | `E0658` on stable rustc | `patch_local_state`, `patch_mmap`, `patch_groups` — rewrite to stable equivalents |
| 2 | jemalloc (`tikv-jemalloc-sys`) won't build | vendored `configure` aborts | `patch_jemalloc` — gate OpenBSD out of the jemalloc `Cargo.toml` target section + the 4 code sites; widen the msvc `None`-fallback stubs to cover OpenBSD so `collect()`/`resident_bytes()` stay defined. Falls back to the system allocator. |
| 3 | `mincore(2)` removed from OpenBSD | `ld: undefined symbol: mincore` at final link | `patch_mincore` — gate the one residency call; report `Ok(0)` (no residency info) on OpenBSD |
| 4 | rustc OOM on heavy crates | `SIGABRT`, "memory allocation failed" compiling `segment`/`qdrant` | Raise the datasize soft limit: `ulimit -d 6291456`. OpenBSD staff class caps it at 1536M by default but the hard cap is far higher, so no `login.conf` edit is needed here. |
| 5 | Fat LTO on the final binary | `SIGABRT` linking `qdrant` (exceeds RAM+swap) | `CARGO_PROFILE_RELEASE_LTO=off` — modest runtime-perf tradeoff for a linkable binary. **With adequate RAM this is unnecessary:** on a 16 GB VM (+ raised datasize) fat LTO links fine and yields a tighter binary (81 MB vs 87 MB), so drop the override there. The script keeps LTO off as the safe default for small hosts. |
| 6 | Small partition | `No space left on device` (~2-3 GB `target/` needed) | Point `CARGO_TARGET_DIR` at a roomy filesystem (see disk enlargement below) |

A linker reports **all** undefined symbols at once, so after fixing `mincore` (the only
one listed) the binary links — walls 1-6 are the complete set for this Qdrant version.

## Build knobs (baked into `build_qdrant_openbsd.sh`)

```sh
ulimit -d 6291456                          # wall 4
CARGO_TARGET_DIR=<roomy-fs>/target \        # wall 6 (if /home is small)
CARGO_BUILD_JOBS=2 \
CARGO_PROFILE_RELEASE_LTO=off \             # wall 5
  cargo build --release --bin qdrant
```

Keep `codegen-units=1` (the profile default) — it produces fewer intermediate object
files, which is leaner on a small disk; memory is fine without LTO given the raised
datasize limit.

## Disk enlargement (wall 6) — non-destructive second disk via libvirt

The workbench VM's `/home` (6.5 GB) is too small for a from-scratch build. Rather than
risky in-place FFS growth (OpenBSD has no online `growfs`), attach a second disk and
build on it. Done entirely through the `libvirt` group's `virsh` (no root on the host):

```sh
# host (member of the libvirt group)
virsh -c qemu:///system vol-create-as default openbsd79-build.qcow2 20G --format qcow2
virsh -c qemu:///system attach-disk openbsd79 \
    /var/lib/libvirt/images/openbsd79-build.qcow2 vdb \
    --persistent --subdriver qcow2 --targetbus virtio
# reboot the guest so OpenBSD enumerates the virtio disk (hotplug is not detected live)
ssh openbsd doas reboot
```

```sh
# guest, after reboot — CONFIRM the new disk's size before newfs (device order can
# flip on reboot; the system disk is the larger one, identified by its DUID in fstab)
doas disklabel sdN                # verify it's the new, empty ~20 GB disk
printf 'a a\n\n\n\nw\nq\n' | doas disklabel -E sdN     # one full-disk partition
doas newfs sdNa
doas mkdir -p /build && doas mount /dev/sdNa /build && doas chown james:james /build
echo "<DUID>.a /build ffs rw,nodev,nosuid 1 2" | doas tee -a /etc/fstab   # persist
```

**Safety:** always confirm the target device's size with `disklabel` before `newfs` — a
reboot can renumber virtio disks (the new disk came up as `sd0`, the system disk as
`sd1`; the system still booted because fstab uses DUIDs, not device names).

## Verify

```sh
/build/target/release/qdrant --version      # or wherever CARGO_TARGET_DIR pointed
doas cp /build/target/release/qdrant /usr/local/bin/qdrant   # install on PATH
```

Then `src/qdrant_server.py` finds it via `shutil.which("qdrant")` and manages its
lifecycle exactly as on the binary platforms.

## Provisioning integration

`tooling/provision_bsd_memory.sh` section 0 calls `build_qdrant_openbsd.sh` on OpenBSD,
so a fresh `setup.sh` run builds and installs Qdrant automatically (a long one-time
compile). The embedding backend on OpenBSD is llama.cpp (GGUF) like everywhere else —
see `docs/dev/memory-architecture.md`.
