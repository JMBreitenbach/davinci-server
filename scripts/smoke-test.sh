#!/usr/bin/env bash
#
# scripts/smoke-test.sh -- post-install sanity check to run ON THE PI
# itself after install.sh. This is the one validation tier that needs
# real hardware: it checks the systemd service, the udev symlink, the
# WiFi onboarding services, and the actual HTTP endpoints on the
# running server -- none of which CI can exercise (see TESTING.md).
#
# Usage (on the Pi, after install.sh has completed):
#   chmod +x scripts/smoke-test.sh
#   ./scripts/smoke-test.sh
#
# Exits 0 if everything passes, 1 if anything fails. Safe to run
# repeatedly -- it's read-only, no state is changed.
#
set -uo pipefail

CONFIG_FILE="/etc/davinci/config.env"
INSTALL_DIR="/opt/davinci"

PASS=0
FAIL=0

check() {
  local desc="$1" cmd="$2"
  if eval "$cmd" >/tmp/smoke-test-last.log 2>&1; then
    echo "  PASS  $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL  $desc"
    sed 's/^/        /' /tmp/smoke-test-last.log | head -5
    FAIL=$((FAIL + 1))
  fi
}

echo "== da Vinci print server smoke test =="
echo ""

if [ -f "$CONFIG_FILE" ]; then
  # shellcheck disable=SC1090
  source "$CONFIG_FILE"
else
  echo "WARNING: $CONFIG_FILE not found -- falling back to install.sh defaults"
fi
DAVINCI_PORT="${DAVINCI_PORT:-5000}"
DAVINCI_DEVICE="${DAVINCI_DEVICE:-/dev/davinci}"

echo "-- Install artifacts"
check "server.py installed"        "[ -f '$INSTALL_DIR/server.py' ]"
check "venv exists"                "[ -x '$INSTALL_DIR/venv/bin/python3' ]"
check "Flask installed in venv"    "'$INSTALL_DIR/venv/bin/pip' show flask"
check "minimover binary present"   "[ -x /usr/local/bin/minimover ]"
check "config.env present"         "[ -f '$CONFIG_FILE' ]"

echo ""
echo "-- systemd services"
check "davinci-server active"      "systemctl is-active --quiet davinci-server"
check "davinci-server enabled"     "systemctl is-enabled --quiet davinci-server"
check "avahi-daemon active"        "systemctl is-active --quiet avahi-daemon"
check "comitup active"             "systemctl is-active --quiet comitup"

echo ""
echo "-- Hardware / udev"
check "udev symlink /dev/davinci exists" "[ -e '$DAVINCI_DEVICE' ]"
if [ ! -e "$DAVINCI_DEVICE" ]; then
  echo "        (expected if the printer is unplugged or the udev rule's"
  echo "         idVendor doesn't match yours -- see README.md)"
fi

echo ""
echo "-- HTTP endpoints (server.py running for real, not mocked)"
BASE="http://localhost:${DAVINCI_PORT}"
check "GET / responds"             "curl -sf '$BASE/' -o /dev/null"
check "GET /files responds"        "curl -sf '$BASE/files' -o /dev/null"
check "GET /status responds"       "curl -sf '$BASE/status' -o /dev/null"
check "GET /printer-status responds" "curl -sf '$BASE/printer-status' -o /dev/null"
check "GET /api/version responds"  "curl -sf '$BASE/api/version' -o /dev/null"

echo ""
echo "-- davinci-reset command"
check "davinci-reset installed"    "[ -x /usr/local/bin/davinci-reset ]"

echo ""
echo "======================================"
echo "  $PASS passed, $FAIL failed"
echo "======================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "Some checks failed. journalctl -u davinci-server -f is a good next"
  echo "place to look; see README.md's 'If something's not working' section."
  exit 1
fi

echo ""
echo "All checks passed. Try uploading a .gcode file at $BASE/ to confirm"
echo "an actual print job end-to-end."
