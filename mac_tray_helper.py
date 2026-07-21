#!/usr/bin/env python3
"""Native macOS menu-bar helper for the Odysseus desktop wrapper.

An NSStatusItem created inside the Qt wrapper process does not render on macOS 26
(Tahoe), and a hand-rolled one via ctypes can't be created before the AppKit run
loop is active. rumps (built on pyobjc) creates the status item inside the app's
launch callback, which is the correct place, so it renders reliably — the same
way standalone menu-bar apps (CrossPaste etc.) do. The wrapper launches this as a
subprocess and sends "open"/"quit" over an AF_UNIX socket the wrapper listens on.

Args: <socket_path> <icon_path>
"""
import os
import socket
import sys
import webbrowser

import rumps

README_URL = "https://github.com/pewdiepie-archdaemon/odysseus#readme"

SOCK_PATH = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/.odysseus_tray.sock")
ICON = sys.argv[2] if len(sys.argv) > 2 and os.path.isfile(sys.argv[2]) else None


def _send(word):
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        s.connect(SOCK_PATH)
        s.sendall(word.encode("utf-8"))
        s.close()
    except Exception:
        pass


class OdysseusTray(rumps.App):
    def __init__(self):
        # No default quit button — we provide Open/Quit that talk to the wrapper.
        # title falls back to text if the icon can't be loaded.
        super().__init__("Odysseus", title=None if ICON else "Odysseus",
                         icon=ICON, quit_button=None)
        self.menu = ["Open Odysseus", "README", None, "Quit Odysseus"]

    @rumps.clicked("Open Odysseus")
    def _open(self, _):
        _send("open")

    @rumps.clicked("README")
    def _readme(self, _):
        webbrowser.open(README_URL)

    @rumps.clicked("Quit Odysseus")
    def _quit(self, _):
        _send("quit")
        rumps.quit_application()


if __name__ == "__main__":
    OdysseusTray().run()
