# da Vinci Print Server

A small self-hosted server that lets you send print jobs to certain
XYZprinting da Vinci 3D printers over your home network — from Cura,
OrcaSlicer, or a plain browser page — instead of XYZprinting's original
XYZware software.

## Why this exists

XYZprinting's da Vinci printers shipped with XYZware: Windows/Mac-only
desktop software, a direct USB tether to one computer, and (on many
models) filament-cartridge checks that fight you if you're not using
XYZ-branded filament. XYZware itself has seen little to no update in
years. If you picked up an old da Vinci printer — yours, or secondhand
— there's a good chance XYZware barely runs on a current OS anymore,
if it installs at all.

This project replaces XYZware with a small print server: point a
spare Raspberry Pi, Banana Pi, or similar small Linux box at the
printer's USB port, run one install script, and you get LAN printing
from any device on your network — slice normally and print like you
would with any modern network-connected printer.

## Supported printers

This repo currently ships one driver: the **da Vinci 1.0 Pro**.

Support for other da Vinci models is bounded by
[minimover](https://github.com/reality-boy/miniMover), the
reverse-engineered protocol library this project shells out to — this
project can only drive a printer minimover already knows how to talk
to. As of writing, minimover supports full send-and-print over its
newer "v3" protocol for:

da Vinci nano, nano w, miniMaker, mini w, mini wA, mini w+, Jr. 1.0,
Jr. 1.0W, Jr. 1.0A, Jr. 1.0 3in1 (and the open-filament variant),
Jr. 1.0 Pro, Jr. 1.0W Pro, Jr. 2.0 Mix, da Vinci 1.0 Pro, da Vinci 1.0
Pro 3in1, and da Vinci 1.0 Super.

minimover can also *convert* files (gcode ↔ .3w) for several older
models, but can't send directly to them yet since their older serial
protocol hasn't been reverse-engineered for printing:

da Vinci 1.0, 1.0A, 1.0 AiO, 1.1 Plus, 2.0 Duo, and 2.0A Duo.

**If your printer is in the first list** and there's no driver for it
here yet, adding one is usually small — see
[CONTRIBUTING.md](CONTRIBUTING.md#adding-support-for-another-printer).
**If it's only in the second list**, minimover itself would need
direct-print support added before this project could drive it —
that's outside this repo, but worth raising in minimover's issue
tracker.

## What you'll need

- A supported da Vinci printer (see above), connected via USB.
- A small, always-on Linux machine to run the server on. A Raspberry
  Pi or Banana Pi is the usual cheap, low-power choice, but nothing
  here is actually ARM-specific — any Debian-based Linux box with a
  spare USB port works (see below).
- Network access for that machine — Ethernet is simplest; WiFi is
  supported with guided first-time setup (see below).

## Supported Linux distributions

`install.sh` is written against **Debian-based distros with systemd**
(Raspberry Pi OS, Armbian, and similar) — it uses `apt-get` for system
packages and installs a systemd service, so that's the assumption
baked into the automation. It doesn't care about CPU architecture:
it's been validated in CI against emulated Debian Bullseye on both
`armv7` (older Pi boards, Banana Pi) and `aarch64` (Pi 4/5), and there's
nothing stopping it from running on an x86 Debian box either.

**It is not guaranteed to work as-is on non-Debian distros** (Arch,
Alpine, Fedora, etc.) — `install.sh`'s package-manager calls are
apt-specific, and one dependency (`comitup`, used for WiFi
onboarding) may not be packaged at all outside Debian's ecosystem;
the script warns and continues without it rather than failing if
that's the case. If you're on a non-Debian system, `server.py` itself
is just a Flask app with no OS-specific code — you can run it directly
(`pip install flask`, then `python3 server.py`) and wire up
autostart/udev/networking by hand, using `install.sh` as a reference
for what needs setting up.

## Install

1. Flash a Debian-based OS (Raspberry Pi OS Lite, Armbian, etc.) to
   your board and get it on your network / reachable over SSH.
2. Connect the printer to the board via USB.
3. Clone this repo onto the board and run the installer:

   ```
   git clone <this-repo-url>
   cd davinci-server
   chmod +x install.sh
   ./install.sh
   ```

That's it — see [why this is a one-command install](#about-as-simple-an-install-as-youll-get)
below for what that one script actually sets up.

4. Once it finishes, the server should be reachable at
   `http://davinci.local:5000`. If `davinci.local` doesn't resolve on
   your network, find the board's IP instead (check your router's
   device list, or run `hostname -I` on the board) and use
   `http://<that-ip>:5000`.

### First-time WiFi setup

If the board isn't on Ethernet and doesn't yet recognize your WiFi
network, it opens its own temporary setup hotspot — no keyboard,
monitor, or SSH needed:

1. On your phone or laptop, look for a WiFi network called
   **"davinci"** and connect to it.
2. A setup page should open automatically (if it doesn't, browse to
   `http://10.41.0.1`).
3. Pick your home WiFi network from the list, enter its password, and
   submit.
4. The board joins your network and reboots — give it about a minute,
   then use `http://davinci.local:5000` as usual.

To switch to a different WiFi network later, SSH in and run
`sudo davinci-reset --wifi`.

## Everyday use

1. Slice your model as normal in Cura or OrcaSlicer, using generic
   PLA/ABS/ASA settings for a 200x200x200mm printer, 0.4mm nozzle — no
   heated-bed chip or filament cartridge required.
2. Either:
   - **Send directly from your slicer:** add a network printer
     connection using the "OctoPrint" option, host = `davinci.local`,
     port `5000`, API key = anything (unless you've set one — see
     below). Enable "upload and print."
   - **Or use the browser UI:** go to `http://davinci.local:5000` in
     any browser on the same network, upload your `.gcode` file, and
     click Print.

What happens when you hit Print: the server converts your `.gcode`
into the printer's native format (via `minimover`) and streams it to
the printer over USB. The UI shows "Converting" then "Printing" while
that happens.

By default, anyone on your LAN can print without authentication. If
the board is reachable beyond your trusted network, set
`DAVINCI_API_KEY` in `/etc/davinci/config.env` and restart the service
to require a key on the API endpoints.

<a id="about-as-simple-an-install-as-youll-get"></a>
## About as simple an install as you'll get

Setting up LAN printing for one of these has historically meant a
patchwork of manual steps — building minimover from source, writing a
systemd unit, figuring out udev rules so the printer has a stable
device path, and separately sorting out WiFi onboarding for a
headless board. `install.sh` does all of that in one idempotent pass:
build minimover, install Flask into a venv, write the systemd service,
install the udev rule, configure mDNS + WiFi onboarding, and install
the reset command below. Re-running it is safe — it won't duplicate
or break anything.

Getting back to a known state is just as scripted. `davinci-reset` is
installed alongside the server for the common "start over" moments,
no SD card re-flash required:

| Command                       | What it does                                                                 |
|--------------------------------|-------------------------------------------------------------------------------|
| `sudo davinci-reset`           | Clears uploaded files and cached conversions, restarts the server. Safe — doesn't touch network or printer settings. |
| `sudo davinci-reset --config`  | Also restores `/etc/davinci/config.env` to install defaults (printer selection, port, API key). |
| `sudo davinci-reset --wifi`    | Forgets saved WiFi networks and reopens the "davinci" setup hotspot so you can join a different network. |
| `sudo davinci-reset --all`     | Does all of the above.                                                        |

Settings you might want to change by hand live in
`/etc/davinci/config.env` (port, API key, which printer driver is
active, the serial device path) — edit that file, then
`sudo systemctl restart davinci-server`.

**Reinstalling from scratch:** if you ever re-flash the board's SD
card, just re-run `install.sh` from a fresh clone of this repo — it
rebuilds and reinstalls everything, including the auto-start service.

## If something's not working

- **Can't reach the web page:** confirm the board has power and a
  network light/connection; try the IP-address fallback above.
- **Upload works but print doesn't start:** the printer may be off,
  out of filament, or the USB cable may be loose — check the
  printer's own screen/LEDs, and try `sudo davinci-reset` to clear a
  stuck job.
- **Logs:** `journalctl -u davinci-server -f`

## For developers

Want to add a driver for another printer, or send a pull request? See
[CONTRIBUTING.md](CONTRIBUTING.md) for the architecture (it's a small
driver interface — `server.py` never talks to `minimover` directly),
how to add a new printer, and what's expected before opening a PR.
Test coverage and what each CI check does and doesn't validate (no
real Pi/printer hardware involved) is documented in
[TESTING.md](TESTING.md).
