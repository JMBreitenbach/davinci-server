# da Vinci 1.0 Pro — Wireless Print Server

This printer has been converted to accept prints over your home network,
instead of the original (defunct) XYZware software.

## What's included

A small computer (Banana Pi) is connected to the printer's USB port and
runs a lightweight print server. It starts automatically when the Pi is
powered on — nothing to install or configure for normal use.

## Everyday use

1. Make sure the Pi is powered on and connected to your network (Ethernet
   is simplest; ask the seller if it's set up for WiFi).
2. Slice your model as normal in Cura or OrcaSlicer.
   - Use PLA/ABS/ASA settings for a generic 200x200x200mm printer,
     0.4mm nozzle, no heated-bed chip / no cartridge required.
3. Either:
   - **Send directly from your slicer:** add a network printer connection
     using the "OctoPrint" option, host = `davinci.local`, port `5000`,
     API key = anything. Enable "upload and print."
   - **Or use the browser UI:** go to `http://davinci.local:5000` in any
     browser on the same network, upload your `.gcode` file, click Print.
4. If `davinci.local` doesn't resolve on your network/router, find the
   Pi's IP address instead (check your router's device list, or connect
   a keyboard/monitor to the Pi and run `hostname -I`) and use
   `http://<that-ip>:5000`.

## First-time setup on a new network

When the Pi doesn't recognize the WiFi network it's on, it creates its
own temporary hotspot so you can point it at your network — no
keyboard, monitor, or technical setup needed:

1. On your phone or laptop, look for a WiFi network called **"davinci"**
   and connect to it.
2. A setup page should open automatically (if it doesn't, open a
   browser and go to `http://10.41.0.1`).
3. Pick your home WiFi network from the list, enter its password, and
   submit.
4. The Pi will join your network and reboot — give it about a minute,
   then go to `http://davinci.local:5000` as usual.

If you ever want to switch it to a different WiFi network later, there
isn't a button for that yet — ask whoever set this up, or see the
"under the hood" section below.

## If something's not working

- **Can't reach the web page:** confirm the Pi has power and a network
  light/connection; try the IP-address fallback above.
- **Upload works but print doesn't start:** the printer may be off, out
  of filament, or the USB cable may be loose — check the printer's own
  screen/LEDs.
- **Reinstalling from scratch:** if you ever re-flash the Pi's SD card
  with a fresh OS, re-run `install.sh` from this same folder — it
  rebuilds and reinstalls everything, including the auto-start service.

## Under the hood (for the technically curious)

- `davinci_server.py` — the print server itself (Python/Flask)
- `install.sh` — one-shot setup script (systemd service, udev rule,
  mDNS hostname)
- The server calls a small open-source utility called `minimover`
  (https://github.com/reality-boy/miniMover) to talk to the printer's
  original USB protocol.
- WiFi onboarding is handled by `comitup` (https://davesteele.github.io/comitup/),
  which manages the network connection via NetworkManager. To force the
  setup hotspot to reappear (e.g. to switch networks), run
  `sudo comitup-cli d` to disconnect, or reset saved networks with
  `nmcli connection show` / `nmcli connection delete <name>`.
- Config lives in `/etc/davinci/config.env` — e.g. change the port or
  require an API key there, then `sudo systemctl restart davinci-server`.
- Logs: `journalctl -u davinci-server -f`
