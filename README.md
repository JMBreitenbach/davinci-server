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

What actually happens when you hit Print: the server converts your
`.gcode` into the printer's native `.3w` format (using `minimover`)
and streams that `.3w` to the printer over USB. The UI shows
"Converting" then "Printing" while that happens.

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

If you ever want to switch it to a different WiFi network later, SSH
in (or plug in a keyboard/monitor) and run:

```
sudo davinci-reset --wifi
```

## Resetting / reconfiguring

A `davinci-reset` command is installed on the Pi for the common "start
over" situations, no SD card re-flash needed:

| Command                       | What it does                                                                 |
|--------------------------------|-------------------------------------------------------------------------------|
| `sudo davinci-reset`           | Clears uploaded files and cached `.3w` conversions, restarts the server. Safe — doesn't touch network or printer settings. |
| `sudo davinci-reset --config`  | Also restores `/etc/davinci/config.env` to install defaults (printer selection, port, API key).       |
| `sudo davinci-reset --wifi`    | Forgets saved WiFi networks and reopens the "davinci" setup hotspot so you can join a different network. |
| `sudo davinci-reset --all`     | Does all of the above.                                                        |

Settings you might want to change by hand live in
`/etc/davinci/config.env` (port, API key, which printer driver is
active, the serial device path) — edit that file, then
`sudo systemctl restart davinci-server`.

## If something's not working

- **Can't reach the web page:** confirm the Pi has power and a network
  light/connection; try the IP-address fallback above.
- **Upload works but print doesn't start:** the printer may be off, out
  of filament, or the USB cable may be loose — check the printer's own
  screen/LEDs, and try `sudo davinci-reset` to clear a stuck job.
- **Reinstalling from scratch:** if you ever re-flash the Pi's SD card
  with a fresh OS, re-run `install.sh` from this same folder — it
  rebuilds and reinstalls everything, including the auto-start service.

## Under the hood (for the technically curious)

- `server.py` — the print server (Python/Flask). Printer-agnostic: it
  only talks to whatever driver is configured, never to `minimover`
  directly.
- `printers/` — the printer driver interface (`base.py`) and the
  concrete da Vinci 1.0 Pro driver (`davinci_1_0_pro.py`), which shells
  out to `minimover` to convert `.gcode` → `.3w` and stream it to the
  printer over USB serial.
- `install.sh` — one-shot setup script (builds `minimover`, sets up the
  systemd service, udev rule, mDNS hostname, and the `davinci-reset`
  command).
- The server calls a small open-source utility called `minimover`
  (https://github.com/reality-boy/miniMover) to talk to the printer's
  original USB protocol.
- WiFi onboarding is handled by `comitup` (https://davesteele.github.io/comitup/),
  which manages the network connection via NetworkManager.
- Config lives in `/etc/davinci/config.env` — e.g. change the port,
  require an API key, or switch which printer driver is active there,
  then `sudo systemctl restart davinci-server`.
- Logs: `journalctl -u davinci-server -f`
- Testing / CI: see [TESTING.md](TESTING.md) -- automated tests run
  against the real Flask app with fake printer hardware, plus a
  QEMU-emulated ARM build check, on every push. `scripts/smoke-test.sh`
  is a post-install checklist to run on real hardware.

### Adding support for another printer

The driver interface (`printers/base.py`) is the whole extension
point. To add a new printer:

1. Create `printers/<your_id>.py` with a class that subclasses
   `PrinterDriver` and implements `convert()`, `print_file()`, and
   `status()`. Use `printers/davinci_1_0_pro.py` as a template — for a
   printer that already speaks plain gcode-over-serial, `convert()` can
   just return the uploaded file unchanged (set `native_extension =
   None`).
2. Register the class in `printers/__init__.py`'s `DRIVERS` dict.
3. Set `DAVINCI_PRINTER=<your_id>` in `/etc/davinci/config.env` and
   `sudo systemctl restart davinci-server`.

`server.py`, the browser UI, and the OctoPrint API shim don't need any
changes — they only ever call the `PrinterDriver` interface.
