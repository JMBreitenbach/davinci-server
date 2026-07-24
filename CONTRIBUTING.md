# Contributing

This doc is for anyone adding a printer driver, poking at the server
itself, or opening a pull request. If you just want to run the server,
see [README.md](README.md) instead.

## Architecture

- `server.py` — the print server (Python/Flask). Printer-agnostic: it
  only ever calls methods on whatever `PrinterDriver` is configured,
  never talks to `minimover` (or any printer-specific tool) directly.
  It also serves a minimal subset of OctoPrint's REST API so Cura's
  and OrcaSlicer's built-in "OctoPrint" network-printing option can
  talk to it.
- `printers/base.py` — the `PrinterDriver` interface. This is the
  entire extension point for supporting a new printer.
- `printers/davinci_1_0_pro.py` — the reference driver, talking to the
  printer via the `minimover` CLI (builds a `.3w` from the uploaded
  `.gcode`, then streams it over USB serial).
- `printers/__init__.py` — the `DRIVERS` registry that maps a
  `DAVINCI_PRINTER` config value to a driver class.
- `install.sh` — one-shot, idempotent setup (builds `minimover`, sets
  up the systemd service, udev rule, mDNS hostname, WiFi onboarding,
  and the `davinci-reset` command).

## Adding support for another printer

Check [README.md's Supported printers section](README.md#supported-printers)
first — this project can only drive printers that
[minimover](https://github.com/reality-boy/miniMover) already supports
direct send-and-print for. If your printer's only convert-capable in
minimover (older serial protocol), a driver here can't fully print to
it until minimover adds that support upstream.

If your printer's on minimover's supported list:

1. Create `printers/<your_id>.py` with a class that subclasses
   `PrinterDriver` and implements `convert()`, `print_file()`, and
   `status()`. Use `printers/davinci_1_0_pro.py` as a template — for a
   printer that already speaks plain gcode-over-serial with no
   conversion step, `convert()` can just return the uploaded file
   unchanged (set `native_extension = None`).
2. Register the class in `printers/__init__.py`'s `DRIVERS` dict.
3. Set `DAVINCI_PRINTER=<your_id>` in `/etc/davinci/config.env` and
   `sudo systemctl restart davinci-server` to test it.

`server.py`, the browser UI, and the OctoPrint API shim don't need any
changes — they only ever call the `PrinterDriver` interface.

## Running things locally

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
python3 server.py          # runs the dev server on :5000
pytest tests/ -v           # run the test suite
```

The test suite runs the real Flask app end-to-end against a fake
`minimover` (see `tests/conftest.py` and
`tests/fixtures/fake_minimover.py`) — no printer or Pi required. See
[TESTING.md](TESTING.md) for what the different test tiers do and
don't cover.

## Before opening a pull request

CI runs automatically on every PR and checks:

- `shellcheck install.sh` — no warnings.
- `pytest tests/` — full suite passing.
- An ARM-emulation build (armv7 + aarch64) that compiles `minimover`
  from source and installs Flask on real ARM userspace.

If you're adding a new driver, please also add tests for it (following
the pattern in `tests/test_server.py`, swap in a fake for your
printer's CLI/protocol the way `fake_minimover.py` does) and update
the printer list in README.md.

If your change touches `install.sh`, `scripts/smoke-test.sh` is worth
running on real hardware if you have access — CI's ARM emulation can't
exercise systemd, udev, or actual USB/WiFi hardware (see TESTING.md
for exactly why).
