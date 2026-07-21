#!/bin/sh
# Detect platform and run the correct native app installer.
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -s)" in
  Linux)
    exec bash "$SCRIPT_DIR/build-linux-app.sh" "$@"
    ;;
  FreeBSD)
    exec bash "$SCRIPT_DIR/build-freebsd-app.sh" "$@"
    ;;
  OpenBSD)
    # build-openbsd-app.sh is #!/bin/sh on purpose — bash is not in the OpenBSD
    # base system. Run it with sh so `./install.sh` works on a stock OpenBSD box.
    exec sh "$SCRIPT_DIR/build-openbsd-app.sh" "$@"
    ;;
  Darwin)
    exec bash "$SCRIPT_DIR/build-mac-app.sh" "$@"
    ;;
  *)
    echo "Unsupported platform: $(uname -s)" >&2
    echo "Supported: Linux, FreeBSD, OpenBSD, macOS (Darwin)" >&2
    exit 1
    ;;
esac
