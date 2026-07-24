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

DAVINCI_USER="${SUDO_USER:-$(whoami)}"
DAVINCI_HOME="$(eval echo "~$DAVINCI_USER")"
INSTALL_DIR="/opt/davinci"
CONFIG_DIR="/etc/davinci"
UPLOAD_DIR="$DAVINCI_HOME/davinci-uploads"
HOSTNAME_MDNS="davinci"

echo "== da Vinci print server installer =="
echo "Installing for user: $DAVINCI_USER"

# --- 1. System packages -----------------------------------------------
echo "-- Installing system packages"
sudo apt-get update -y
sudo apt-get install -y build-essential git python3 python3-pip python3-venv avahi-daemon
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
sudo cp "$(dirname "$0")/davinci_server.py" "$INSTALL_DIR/davinci_server.py"

echo "-- Setting up a virtualenv for Flask"
sudo python3 -m venv "$INSTALL_DIR/venv"
sudo "$INSTALL_DIR/venv/bin/pip" install --upgrade pip flask

mkdir -p "$UPLOAD_DIR"

# --- 4. Config file -------------------------------------------------------
echo "-- Writing config to $CONFIG_DIR/config.env"
sudo mkdir -p "$CONFIG_DIR"
sudo tee "$CONFIG_DIR/config.env" > /dev/null <<EOF
DAVINCI_MINIMOVER_BIN=/usr/local/bin/minimover
DAVINCI_SERIAL_DEVICE=/dev/davinci
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
sudo udevadm control --reload-rules
sudo udevadm trigger

sudo usermod -aG dialout "$DAVINCI_USER"

# --- 6. systemd service ---------------------------------------------------
echo "-- Installing systemd service"
sudo tee /etc/systemd/system/davinci-server.service > /dev/null <<EOF
[Unit]
Description=da Vinci 1.0 Pro LAN print server
After=network-online.target
Wants=network-online.target

[Service]
EnvironmentFile=$CONFIG_DIR/config.env
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/davinci_server.py
Restart=on-failure
RestartSec=3
User=$DAVINCI_USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now davinci-server

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
sudo systemctl enable --now comitup
sudo systemctl enable --now avahi-daemon

echo ""
echo "== Done =="
echo "Server should be reachable at: http://$HOSTNAME_MDNS.local:5000"
echo "(fallback: http://$(hostname -I | awk '{print $1}'):5000)"
echo ""
echo "Check status with: sudo systemctl status davinci-server"
echo "View logs with:    journalctl -u davinci-server -f"
echo ""
echo "IMPORTANT: verify /etc/udev/rules.d/99-davinci.rules matches your"
echo "printer's actual USB vendor ID before relying on /dev/davinci."
