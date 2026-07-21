#!/usr/bin/env python3
"""Native macOS menu-bar helper for the Odysseus desktop wrapper.

An NSStatusItem created inside the Qt wrapper process does not render on macOS 26
(Tahoe), and a hand-rolled one via ctypes can't be created before the AppKit run
loop is active. rumps (built on pyobjc) creates the status item inside the app's
launch callback, which is the correct place, so it renders reliably — the same
way standalone menu-bar apps (CrossPaste etc.) do.

The wrapper owns server state, so this helper is deliberately thin:
- state-dependent / page / lifecycle actions (Open, Settings, Shortcut Keys,
  Expose to Network, Restart, About, Quit) are sent to the wrapper as one-word
  verbs over an AF_UNIX socket;
- purely local actions (Open in Browser, Copy Server URL, View Logs, README)
  are handled here, since they need nothing the wrapper alone knows;
- a periodic "status" query keeps the status line and the Expose checkmark live.

Args: <socket_path> <icon_path> <log_dir>
"""
import os
import socket
import subprocess
import sys
import webbrowser

import rumps

README_URL = "https://github.com/odysseus-dev/odysseus#readme"

SOCK_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.odysseus_tray.sock")
ICON = sys.argv[2] if len(sys.argv) > 2 and os.path.isfile(sys.argv[2]) else None
LOG_DIR = sys.argv[3] if len(sys.argv) > 3 else ""


def _send(word):
    """Fire-and-forget a verb to the wrapper."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(SOCK_PATH)
        s.sendall(word.encode("utf-8"))
        s.close()
    except Exception:
        pass


def _query(word):
    """Send a verb and read the wrapper's reply (used for 'status')."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(SOCK_PATH)
        s.sendall(word.encode("utf-8"))
        data = s.recv(128).decode("utf-8", "ignore")
        s.close()
        return data
    except Exception:
        return ""


class OdysseusTray(rumps.App):
    def __init__(self):
        # No default quit button — we provide our own that talks to the wrapper.
        super().__init__("Odysseus", title=None if ICON else "Odysseus",
                         icon=ICON, quit_button=None)
        # Last-known reachable "host:port" from a status poll; drives the local
        # browser/copy actions so they never guess an address.
        self._hostport = "localhost:7000"

        self._status = rumps.MenuItem("Odysseus")   # disabled (no callback)
        self._expose = rumps.MenuItem("Expose to Network", callback=self._toggle_expose)
        self.menu = [
            self._status,
            None,
            rumps.MenuItem("Open Odysseus", callback=self._open),
            rumps.MenuItem("Open in Browser", callback=self._browser),
            rumps.MenuItem("Copy Server URL", callback=self._copy_url),
            None,
            rumps.MenuItem("Settings…", callback=self._settings),
            rumps.MenuItem("Shortcut Keys…", callback=self._shortcuts),
            self._expose,
            None,
            rumps.MenuItem("View Logs", callback=self._logs),
            rumps.MenuItem("Restart Server", callback=self._restart),
            None,
            rumps.MenuItem("README", callback=self._readme),
            rumps.MenuItem("About Odysseus", callback=self._about),
            None,
            rumps.MenuItem("Quit Odysseus", callback=self._quit),
        ]
        # Poll server state so the status line + checkmark stay live. rumps.Timer
        # callbacks run on the main run loop, so touching menu items here is safe.
        self._timer = rumps.Timer(self._poll, 3)
        self._timer.start()
        self._poll(None)

    # ── live state ──
    def _poll(self, _):
        reply = _query("status")
        if not reply:
            self._status.title = "○ Not responding"
            return
        parts = reply.split("|")
        running = parts[0] == "1"
        hostport = parts[1] if len(parts) > 1 else ""
        expose = len(parts) > 2 and parts[2] == "1"
        if hostport:
            self._hostport = hostport
        self._status.title = f"● Running — {hostport}" if running else "○ Stopped"
        self._expose.state = 1 if expose else 0

    def _url(self):
        return f"http://{self._hostport}"

    # ── local actions (need nothing only the wrapper knows) ──
    def _browser(self, _):
        webbrowser.open(self._url())

    def _copy_url(self, _):
        try:
            p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
            p.communicate(self._url().encode("utf-8"))
        except Exception:
            pass

    def _logs(self, _):
        if LOG_DIR:
            subprocess.Popen(["open", LOG_DIR])

    def _readme(self, _):
        webbrowser.open(README_URL)

    # ── routed to the wrapper ──
    def _open(self, _):
        _send("open")

    def _settings(self, _):
        _send("settings")

    def _shortcuts(self, _):
        _send("shortcuts")

    def _toggle_expose(self, _):
        # The wrapper owns the state (and the confirm dialog); it flips and
        # restarts, then the next poll updates our checkmark.
        _send("expose")

    def _restart(self, _):
        _send("restart")

    def _about(self, _):
        _send("about")

    def _quit(self, _):
        _send("quit")
        rumps.quit_application()


if __name__ == "__main__":
    OdysseusTray().run()
