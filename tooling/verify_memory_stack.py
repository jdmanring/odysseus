#!/usr/bin/env python3
"""Verify the memory / RAG stack (chromadb + fastembed) actually loads.

Run after installing requirements.txt. `fastembed` powers semantic memory, RAG,
and personal-doc retrieval; it pulls in `onnxruntime`, whose NATIVE runtime has
platform prerequisites pip cannot provide:

  - Windows: the Microsoft Visual C++ Redistributable (onnxruntime's .pyd links
    against the MSVC runtime; without it the DLL load fails).
  - FreeBSD: fastembed's `py-rust-stemmers` dependency has no prebuilt binary and
    must be compiled with the Rust toolchain.

A silent failure here demotes semantic memory and RAG to keyword search, so the
installers check it explicitly and print an actionable fix rather than letting it
degrade unnoticed at runtime.

Exit 0 = memory stack healthy; exit 1 = degraded (with remediation printed).
"""
import platform
import sys


def _import_error(mod):
    try:
        __import__(mod)
        return None
    except Exception as e:  # ImportError, DLL load failure, anything
        return e


def _fastembed_fix(err) -> str:
    msg = str(err)
    osname = platform.system()
    if osname == "Windows" and ("DLL load failed" in msg or "onnxruntime" in msg):
        return ("onnxruntime's native runtime needs the Microsoft Visual C++ "
                "Redistributable. Install it (setup.ps1 does this automatically):\n"
                "      https://aka.ms/vs/17/release/vc_redist.x64.exe  "
                "(run with /install /quiet /norestart)")
    if "py-rust-stemmers" in msg or "Rust not found" in msg or "cargo" in msg:
        return ("fastembed's py-rust-stemmers dependency has no FreeBSD binary and "
                "must be built once with Rust:\n"
                "      doas pkg install rust && venv/bin/pip install fastembed && "
                "doas pkg remove rust")
    if isinstance(err, ModuleNotFoundError):
        return "install it into the venv:  pip install fastembed"
    return "reinstall:  pip install --force-reinstall fastembed onnxruntime"


def main() -> int:
    problems = []

    err = _import_error("chromadb")
    if err is not None:
        problems.append(("chromadb-client", err, "pip install chromadb-client"))

    # Embedding backend: fastembed (onnxruntime) is the default; where it can't
    # run (FreeBSD has no onnxruntime Python binding) the app falls back to the
    # llama.cpp backend, which is equally valid. So the stack is healthy if
    # EITHER loads. Importing fastembed exercises onnxruntime's native load.
    backend = None
    fe_err = _import_error("fastembed") or _import_error("onnxruntime")
    if fe_err is None:
        backend = "fastembed"
    else:
        lc_err = _import_error("llama_cpp")
        if lc_err is None:
            backend = "llama.cpp"
        else:
            problems.append((
                "embedding backend", fe_err,
                _fastembed_fix(fe_err) + "  OR install the llama.cpp fallback "
                "(FreeBSD: pkg install py312-llama-cpp-python).",
            ))

    if not problems:
        print(f"ok  Memory stack healthy - chromadb + {backend} embedding backend load.")
        return 0

    print("WARNING: the memory / RAG stack is DEGRADED. Semantic memory, RAG, and")
    print("         personal-doc retrieval will fall back to keyword search until")
    print("         this is fixed:")
    for name, err, fix in problems:
        print(f"  - {name}: {type(err).__name__}: {err}")
        print(f"    fix: {fix}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
