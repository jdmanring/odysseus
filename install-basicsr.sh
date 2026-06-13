#!/usr/bin/env bash
# Install basicsr with a Python 3.13+ compatible patch, then install realesrgan.
# basicsr's setup.py uses exec()+locals() which broke in Python 3.13/3.14.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
VENV_PIP="$REPO/venv/bin/pip"
VENV_PYTHON="$REPO/venv/bin/python"
TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

echo "Downloading basicsr 1.4.2 source..."
curl -s -L "https://files.pythonhosted.org/packages/source/b/basicsr/basicsr-1.4.2.tar.gz" \
    -o "$TMPDIR/basicsr.tar.gz"
tar -xzf "$TMPDIR/basicsr.tar.gz" -C "$TMPDIR"

export BASICSR_SRC="$TMPDIR/basicsr-1.4.2"

echo "Patching setup.py for Python 3.13+ compatibility..."
"$VENV_PYTHON" - <<'PYEOF'
import pathlib, sys, os
setup = pathlib.Path(os.environ["BASICSR_SRC"]) / "setup.py"
src = setup.read_text()
old = ("def get_version():\n"
       "    with open(version_file, 'r') as f:\n"
       "        exec(compile(f.read(), version_file, 'exec'))\n"
       "    return locals()['__version__']")
new = ("def get_version():\n"
       "    with open(version_file, 'r') as f:\n"
       "        ns = {}\n"
       "        exec(compile(f.read(), version_file, 'exec'), ns)\n"
       "    return ns['__version__']")
if old not in src:
    print("ERROR: get_version() pattern not found.")
    sys.exit(1)
setup.write_text(src.replace(old, new))
print("Patched.")
PYEOF

echo "Building patched basicsr wheel..."
cd "$TMPDIR/basicsr-1.4.2"
"$VENV_PYTHON" setup.py bdist_wheel --quiet 2>&1 | tail -3

WHEEL=$(find "$TMPDIR/basicsr-1.4.2/dist" -name "basicsr-*.whl" | head -1)
if [[ -z "$WHEEL" ]]; then
    echo "ERROR: wheel build failed."
    exit 1
fi

echo "Installing patched basicsr..."
"$VENV_PIP" install --quiet --no-deps "$WHEEL"
echo "basicsr installed."

echo "Installing realesrgan..."
"$VENV_PIP" install --quiet realesrgan
echo "realesrgan installed."
