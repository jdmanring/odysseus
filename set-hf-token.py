#!/usr/bin/env python3
"""Write a HuggingFace token directly to cookbook_state.json, bypassing the UI race."""
import json, sys
from pathlib import Path

repo = Path(__file__).resolve().parent
key_path = repo / "data" / ".app_key"
state_path = repo / "data" / "cookbook_state.json"

if not key_path.exists():
    print("ERROR: data/.app_key not found. Run Odysseus at least once first.")
    sys.exit(1)

try:
    from cryptography.fernet import Fernet
except ImportError:
    print("ERROR: cryptography package not available.")
    print("Run: venv/bin/pip install cryptography")
    sys.exit(1)

print("Paste your HuggingFace token and press Enter: ", end="", flush=True)
token = input().strip()
if not token:
    print("No token entered.")
    sys.exit(1)

key = key_path.read_bytes()
encrypted = Fernet(key).encrypt(token.encode()).decode()

state = {}
if state_path.exists():
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        pass

if not isinstance(state.get("env"), dict):
    state["env"] = {}

state["env"]["hfToken"] = encrypted

state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
masked = f"{token[:4]}...{token[-4:]}" if len(token) > 8 else "stored"
print(f"Token saved ({masked}). Restart Odysseus for it to take effect.")
