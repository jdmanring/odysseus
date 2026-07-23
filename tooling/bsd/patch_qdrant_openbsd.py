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
    ok = patch_local_state(root) and patch_mmap(root)
    if not ok:
        print("patch: expected Qdrant source files not found under", root, file=sys.stderr)
        return 1
    print("patch: applied OpenBSD stable-Rust fixes to", root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
