#!/usr/bin/env bash
#
# install.sh -- turnkey setup for the da Vinci 1.0 Pro LAN print server
#
# Run this once on a fresh Banana Pi (any reasonably modern Debian-based
# distro -- Armbian, Raspberry Pi OS, etc. all work; nothing here depends
# on a specific one). Safe to re-run; it's idempotent.
#
#   curl -fsSL <wherever-you-host-this>/install.sh | bash
#     -- or --
#   chmod +x install.sh && ./install.sh
#
set -euo pipefail

# --image-build (or DAVINCI_IMAGE_BUILD=1) skips the steps that need a
# live running system -- starting services and reloading udev -- because
# neither exists inside a pi-gen chroot at build time. The rest of this
# script (packages, minimover build, config/unit files, udev rule
# install) is identical either way; those steps take effect on first
# real boot instead. See pi-gen/stage-davinci for the caller.
IMAGE_BUILD="${DAVINCI_IMAGE_BUILD:-0}"
for arg in "$@"; do
  case "$arg" in
    --image-build) IMAGE_BUILD=1 ;;
    *) echo "Unknown option: $arg (expected --image-build)"; exit 1 ;;
  esac
done

DAVINCI_USER="${DAVINCI_USER:-${SUDO_USER:-$(whoami)}}"
DAVINCI_HOME="$(eval echo "~$DAVINCI_USER")"
INSTALL_DIR="/opt/davinci"
CONFIG_DIR="/etc/davinci"
UPLOAD_DIR="$DAVINCI_HOME/davinci-uploads"
HOSTNAME_MDNS="davinci"
DEFAULT_PRINTER="davinci_1_0_pro"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "== da Vinci print server installer =="
echo "Installing for user: $DAVINCI_USER"

# --- 1. System packages -----------------------------------------------
echo "-- Installing system packages"
sudo apt-get update -y
sudo apt-get install -y build-essential git python3 python3-pip python3-venv avahi-daemon network-manager
if ! sudo apt-get install -y comitup; then
  echo "   WARNING: 'comitup' isn't in this distro's apt repos."
  echo "   Buyers won't get automatic WiFi onboarding until this is"
  echo "   resolved -- see https://davesteele.github.io/comitup/ for"
  echo "   manual install options, or fall back to giving buyers"
  echo "   'sudo nmtui' instructions instead (less turnkey)."
fi

# --- 2. Build minimover -------------------------------------------------
if ! command -v minimover >/dev/null 2>&1; then
  echo "-- Building minimover from source"
  BUILD_DIR="$(mktemp -d)"
  git clone --depth 1 https://github.com/reality-boy/miniMover.git "$BUILD_DIR/miniMover"
  make -C "$BUILD_DIR/miniMover/miniMoverConsole"
  sudo install -m 755 "$BUILD_DIR/miniMover/miniMoverConsole/minimover" /usr/local/bin/minimover
  rm -rf "$BUILD_DIR"
else
  echo "-- minimover already installed, skipping build"
fi

# --- 3. Install the web server ------------------------------------------
echo "-- Installing web server to $INSTALL_DIR"
sudo mkdir -p "$INSTALL_DIR"
sudo cp "$SCRIPT_DIR/server.py" "$INSTALL_DIR/server.py"
sudo rm -rf "$INSTALL_DIR/printers"
sudo cp -r "$SCRIPT_DIR/printers" "$INSTALL_DIR/printers"

echo "-- Setting up a virtualenv for Flask"
sudo python3 -m venv "$INSTALL_DIR/venv"
sudo "$INSTALL_DIR/venv/bin/pip" install --upgrade pip flask

mkdir -p "$UPLOAD_DIR" "$UPLOAD_DIR/.converted"
# Not sudo-prefixed above: normally this script runs as the target
# user, so plain mkdir already gets the right ownership. That's not
# true under --image-build, where the whole script runs as root inside
# a chroot -- so make ownership explicit either way.
sudo chown -R "$DAVINCI_USER:$DAVINCI_USER" "$UPLOAD_DIR"

# --- 4. Config file -------------------------------------------------------
echo "-- Writing config to $CONFIG_DIR/config.env"
sudo mkdir -p "$CONFIG_DIR"
sudo tee "$CONFIG_DIR/config.env" > /dev/null <<EOF
# Which printer driver to use -- see /opt/davinci/printers/__init__.py
# for the list of registered drivers. Adding a new printer means
# writing one new driver module there; nothing else needs to change.
DAVINCI_PRINTER=$DEFAULT_PRINTER
DAVINCI_MINIMOVER_BIN=/usr/local/bin/minimover
DAVINCI_DEVICE=/dev/davinci
DAVINCI_UPLOAD_DIR=$UPLOAD_DIR
DAVINCI_PORT=5000
# Set a key below and uncomment to require it (recommended if the Pi
# is reachable beyond your trusted LAN):
# DAVINCI_API_KEY=changeme123
EOF

# --- 5. udev rule for a stable device name + non-root permissions --------
#
# Gives the printer a stable /dev/davinci symlink regardless of which
# ttyACM/ttyUSB number it enumerates as, and makes it group-accessible
# instead of root-only.
echo "-- Installing udev rule"
sudo tee /etc/udev/rules.d/99-davinci.rules > /dev/null <<'EOF'
SUBSYSTEM=="tty", ATTRS{idVendor}=="0483", MODE="0666", GROUP="dialout", SYMLINK+="davinci"
EOF
echo "   NOTE: the idVendor above (0483, STMicro) is a common default for"
echo "   these boards but isn't confirmed for this exact printer. Check"
echo "   yours with: udevadm info -a -n /dev/ttyACM0 | grep idVendor"
echo "   and edit /etc/udev/rules.d/99-davinci.rules if it differs."
if [ "$IMAGE_BUILD" = "1" ]; then
  echo "   (--image-build: skipping udevadm reload/trigger -- no live udev in a chroot)"
else
  sudo udevadm control --reload-rules
  sudo udevadm trigger
fi

sudo usermod -aG dialout "$DAVINCI_USER"

# --- 6. systemd service ---------------------------------------------------
echo "-- Installing systemd service"
sudo tee /etc/systemd/system/davinci-server.service > /dev/null <<EOF
[Unit]
Description=da Vinci print server
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=$CONFIG_DIR/config.env
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/server.py
Restart=on-failure
RestartSec=3
User=$DAVINCI_USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
if [ "$IMAGE_BUILD" = "1" ]; then
  echo "   (--image-build: enabling davinci-server for boot, not starting it now)"
  sudo systemctl enable davinci-server
else
  sudo systemctl enable --now davinci-server
fi

# --- 7. WiFi provisioning (comitup) + mDNS hostname ----------------------
#
# comitup gives first-time buyers a way to join their own WiFi without
# SSH or a keyboard: if the Pi isn't connected to a known network on
# boot, it broadcasts a "davinci" hotspot with a captive portal for
# picking a network and entering the password. Once connected, comitup
# sets the hostname to match, so davinci.local keeps working either way.
#
# Requires the Pi to have a WiFi radio (onboard or USB dongle) capable
# of AP mode.
echo "-- Configuring comitup (WiFi onboarding) and mDNS hostname"
sudo tee /etc/comitup.conf > /dev/null <<EOF
ap_name: $HOSTNAME_MDNS
EOF
if [ "$IMAGE_BUILD" = "1" ]; then
  echo "   (--image-build: enabling comitup + avahi-daemon for boot, not starting now)"
  sudo systemctl enable comitup
  sudo systemctl enable avahi-daemon
else
  sudo systemctl enable --now comitup
  sudo systemctl enable --now avahi-daemon
fi

# --- 8. davinci-reset command ----------------------------------------------
#
# One command for the two "easy to configure/reset" scenarios that
# come up after first setup: clearing a stuck job/upload queue, and
# starting over on config or WiFi without re-flashing the SD card.
echo "-- Installing davinci-reset command"
sudo tee /usr/local/bin/davinci-reset > /dev/null <<EOF
#!/usr/bin/env bash
# davinci-reset -- quick reset commands for the da Vinci print server.
#
# Usage:
#   davinci-reset            Clear uploaded files + cached conversions and
#                             restart the server. Safe -- doesn't touch
#                             network or printer config.
#   davinci-reset --config   Also restore $CONFIG_DIR/config.env to the
#                             defaults shipped by install.sh.
#   davinci-reset --wifi     Forget saved WiFi networks and re-open the
#                             "$HOSTNAME_MDNS" setup hotspot (comitup) so you
#                             can re-onboard onto a different network.
#   davinci-reset --all      Do all of the above.
set -euo pipefail

CONFIG_DIR="$CONFIG_DIR"
UPLOAD_DIR="$UPLOAD_DIR"

do_files() {
  echo "-- Clearing uploaded files and cached conversions"
  find "\$UPLOAD_DIR" -maxdepth 1 -type f -delete 2>/dev/null || true
  if [ -d "\$UPLOAD_DIR/.converted" ]; then
    find "\$UPLOAD_DIR/.converted" -maxdepth 1 -type f -delete 2>/dev/null || true
  fi
}

do_config() {
  echo "-- Restoring \$CONFIG_DIR/config.env to defaults"
  tee "\$CONFIG_DIR/config.env" > /dev/null <<INNEREOF
DAVINCI_PRINTER=$DEFAULT_PRINTER
DAVINCI_MINIMOVER_BIN=/usr/local/bin/minimover
DAVINCI_DEVICE=/dev/davinci
DAVINCI_UPLOAD_DIR=$UPLOAD_DIR
DAVINCI_PORT=5000
# DAVINCI_API_KEY=changeme123
INNEREOF
}

do_wifi() {
  echo "-- Forgetting saved WiFi networks and reopening setup hotspot"
  if command -v comitup-cli >/dev/null 2>&1; then
    comitup-cli d || true
  fi
  nmcli -t -f NAME,TYPE connection show 2>/dev/null | awk -F: '\$2=="802-11-wireless"{print \$1}' | while read -r name; do
    nmcli connection delete "\$name" || true
  done
}

DO_CONFIG=0
DO_WIFI=0
for arg in "\$@"; do
  case "\$arg" in
    --config) DO_CONFIG=1 ;;
    --wifi) DO_WIFI=1 ;;
    --all) DO_CONFIG=1; DO_WIFI=1 ;;
    *) echo "Unknown option: \$arg (expected --config, --wifi, or --all)"; exit 1 ;;
  esac
done

if [ "\$EUID" -ne 0 ]; then
  echo "Run this with sudo: sudo davinci-reset \$*"
  exit 1
fi

do_files
[ "\$DO_CONFIG" = "1" ] && do_config
[ "\$DO_WIFI" = "1" ] && do_wifi

echo "-- Restarting davinci-server"
systemctl restart davinci-server
echo "== Done =="
EOF
sudo chmod 755 /usr/local/bin/davinci-reset

echo ""
echo "== Done =="
echo "Server should be reachable at: http://$HOSTNAME_MDNS.local:5000"
echo "(fallback: http://$(hostname -I | awk '{print $1}'):5000)"
echo ""
echo "Check status with: sudo systemctl status davinci-server"
echo "View logs with:    journalctl -u davinci-server -f"
echo "Reset with:         sudo davinci-reset [--config] [--wifi] [--all]"
echo ""
echo "IMPORTANT: verify /etc/udev/rules.d/99-davinci.rules matches your"
echo "printer's actual USB vendor ID before relying on /dev/davinci."
