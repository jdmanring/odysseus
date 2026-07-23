#!/usr/bin/env python3
"""Patch a Qdrant source tree so it builds on OpenBSD's stable Rust.

Qdrant's `common` crate uses three nightly-only std features that OpenBSD's
packaged stable rustc rejects (E0658). Each has an exact stable equivalent — this
is a behaviour-preserving downgrade, not a workaround:

  * `<*const T>::as_ref_unchecked()`  ->  `&*ptr`
  * `<*mut T>::as_mut_unchecked()`    ->  `&mut *ptr`
  * `cfg_select! { linux => {A} _ => {B} }`  ->  `#[cfg]` / `#[cfg(not)]` blocks
    (the arms declare ptr/ptr_seq/len used after the block, so the bindings are
    hoisted and assigned in whichever arm compiles).

Usage: patch_qdrant_openbsd.py <qdrant-src-dir>   (idempotent).
"""
import sys
from pathlib import Path

REPLACEMENT = '''        let ptr;
        let ptr_seq;
        let len;
        #[cfg(target_os = "linux")]
        {
            let remap_options = memmap2::RemapOptions::new().may_move(true);
            unsafe {
                mmap.remap(new_len as usize, remap_options)?;
                mmap_seq.as_mut().map(|m| m.remap(new_len as usize, remap_options)).transpose()?;
            };
            ptr = SendSyncPtr(mmap.as_mut_ptr());
            ptr_seq = mmap_seq.as_ref().map(|m| SendSyncPtr(m.as_mut_ptr())).unwrap_or(ptr);
            len = new_len as usize;
        }
        #[cfg(not(target_os = "linux"))]
        {
            *mmap = open_mmap(
                self.path.as_ref(),
                self.writeable,
                self.populate,
                self.advice,
            )?;
            ptr = SendSyncPtr(mmap.as_mut_ptr());
            if let Some(mmap_seq) = mmap_seq.as_mut() {
                let mmap_seq_ = open_mmap(
                    self.path(),
                    false,
                    false,
                    AdviceSetting::Advice(Advice::Sequential),
                )?;
                **mmap_seq = mmap_seq_;
                len = std::cmp::min(mmap.len(), mmap_seq.len());
                ptr_seq = SendSyncPtr(mmap_seq.as_mut_ptr());
            } else {
                len = mmap.len();
                ptr_seq = ptr;
            }
        }'''


def patch_local_state(root: Path) -> bool:
    f = root / "lib/common/common/src/universal_io/simple_disk_cache/local_state.rs"
    if not f.exists():
        return False
    s = f.read_text()
    s2 = (s.replace("self.mmap.get().as_ref_unchecked()", "&*self.mmap.get()")
            .replace("self.mmap.get().as_mut_unchecked()", "&mut *self.mmap.get()"))
    if s2 != s:
        f.write_text(s2)
    return True


def patch_groups(root: Path) -> bool:
    """`if let` guards in a match are unstable; collapse the three Number arms
    into one arm with a nested if/else-if/else (identical behaviour)."""
    f = root / "lib/segment/src/data_types/groups.rs"
    if not f.exists():
        return False
    s = f.read_text()
    old = (
        '            JsonValue::Number(n) if let Some(n_u64) = n.as_u64() => Ok(Self::NumberU64(n_u64)),\n'
        '            JsonValue::Number(n) if let Some(n_i64) = n.as_i64() => Ok(Self::NumberI64(n_i64)),\n'
        '            JsonValue::Number(_) => Err(()),\n'
    )
    new = (
        '            JsonValue::Number(n) => {\n'
        '                if let Some(n_u64) = n.as_u64() {\n'
        '                    Ok(Self::NumberU64(n_u64))\n'
        '                } else if let Some(n_i64) = n.as_i64() {\n'
        '                    Ok(Self::NumberI64(n_i64))\n'
        '                } else {\n'
        '                    Err(())\n'
        '                }\n'
        '            }\n'
    )
    if old in s:
        f.write_text(s.replace(old, new))
    return True


def patch_jemalloc(root: Path) -> bool:
    """Gate jemalloc out of the OpenBSD build.

    `tikv-jemalloc-sys` bundles jemalloc's `configure`, which does not build on
    OpenBSD (it aborts in the vendored autotools step). jemalloc is only a
    perf/telemetry allocator here, so OpenBSD falls back to the system allocator —
    a behaviour-preserving downgrade (the memory-telemetry readers already have a
    "no jemalloc" path that returns None).

    Three edits, all cfg-only:
      * Cargo.toml: exclude OpenBSD from the jemalloc-deps target section, so
        `tikv-jemallocator` / `tikv-jemalloc-ctl` are never pulled (and their
        jemalloc-sys build never runs).
      * main.rs, memory_telemetry.rs: add `not(target_os = "openbsd")` to every
        jemalloc-positive cfg (`all(not(msvc), any(x86_64, aarch64))`), so the
        jemalloc code paths compile out on OpenBSD.
      * memory_telemetry.rs: widen the `#[cfg(target_env = "msvc")]` fallback
        (the None-returning `collect`/`resident_bytes` stubs) to also cover
        OpenBSD — otherwise removing the jemalloc definitions would leave those
        functions undefined.

    Line-oriented so it works regardless of the block's indentation, and
    idempotent (skips a line already followed by the openbsd clause / already
    widened).
    """
    ok = True

    # --- Cargo.toml: exclude OpenBSD from the jemalloc target section ---------
    cargo = root / "Cargo.toml"
    if cargo.exists():
        s = cargo.read_text()
        needle = 'cfg(all(not(target_env = "msvc"), any(target_arch = "x86_64"'
        repl = ('cfg(all(not(target_env = "msvc"), not(target_os = "openbsd"), '
                'any(target_arch = "x86_64"')
        if needle in s and repl not in s:
            cargo.write_text(s.replace(needle, repl))
    else:
        ok = False

    # --- Rust cfg sites -------------------------------------------------------
    for rel in ("src/main.rs",
                "src/common/telemetry_ops/memory_telemetry.rs"):
        f = root / rel
        if not f.exists():
            ok = False
            continue
        lines = f.read_text().split("\n")
        out = []
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Widen the msvc-only fallback to include OpenBSD.
            if stripped == '#[cfg(target_env = "msvc")]':
                indent = line[: len(line) - len(line.lstrip())]
                out.append(indent + '#[cfg(any(target_env = "msvc", target_os = "openbsd"))]')
                continue
            out.append(line)
            # After the jemalloc-positive `not(msvc)` clause, insert the openbsd
            # exclusion (unless it's already the next line).
            if stripped == 'not(target_env = "msvc"),':
                indent = line[: len(line) - len(line.lstrip())]
                nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                if nxt != 'not(target_os = "openbsd"),':
                    out.append(indent + 'not(target_os = "openbsd"),')
        f.write_text("\n".join(out))

    return ok


def patch_mincore(root: Path) -> bool:
    """Gate the `mincore(2)` page-residency call for OpenBSD.

    `MmapFile::resident_bytes` measures page-cache residency via `mincore`, which
    OpenBSD removed from libc years ago — the symbol is undefined at final link.
    On OpenBSD, skip the syscall and report no residency info (Ok(0)): a
    point-in-time RAM-residency estimate degrading to zero is harmless (it only
    feeds a memory telemetry approximation), and it keeps the binary linkable.
    Idempotent.
    """
    f = root / "lib/common/common/src/universal_io/mmap/mod.rs"
    if not f.exists():
        return False
    s = f.read_text()
    old = ("        let ret = unsafe { nix::libc::mincore(self.ptr.0.cast(), "
           "len, vec.as_mut_ptr().cast()) };\n")
    new = ('        #[cfg(not(target_os = "openbsd"))]\n'
           "        let ret = unsafe { nix::libc::mincore(self.ptr.0.cast(), "
           "len, vec.as_mut_ptr().cast()) };\n"
           "        // OpenBSD removed the mincore(2) syscall; report no residency\n"
           "        // info (all pages non-resident -> Ok(0)) rather than fail to link.\n"
           '        #[cfg(target_os = "openbsd")]\n'
           "        let ret = { let _ = &mut vec; 0 };\n")
    if old in s and new not in s:
        f.write_text(s.replace(old, new))
    return True


def patch_mmap(root: Path) -> bool:
    f = root / "lib/common/common/src/universal_io/mmap/mod.rs"
    if not f.exists():
        return False
    lines = f.read_text().split("\n")
    if "cfg_select!" not in "\n".join(lines):
        return True  # already patched / not present
    start = next(i for i, l in enumerate(lines) if l.strip() == "cfg_select! {")
    depth = 0
    end = None
    for i in range(start, len(lines)):
        depth += lines[i].count("{") - lines[i].count("}")
        if depth == 0 and i > start:
            end = i
            break
    if end is None:
        raise SystemExit("could not brace-match the cfg_select! block")
    lines[start:end + 1] = REPLACEMENT.split("\n")
    f.write_text("\n".join(lines))
    return True


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: patch_qdrant_openbsd.py <qdrant-src-dir>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1])
    # Evaluate each independently (no short-circuit) so one missing file doesn't
    # silently skip the rest.
    results = [
        patch_local_state(root),
        patch_mmap(root),
        patch_groups(root),
        patch_jemalloc(root),
        patch_mincore(root),
    ]
    ok = all(results)
    if not ok:
        print("patch: expected Qdrant source files not found under", root, file=sys.stderr)
        return 1
    print("patch: applied OpenBSD stable-Rust fixes to", root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
