# Testing / validation

This project talks to real 3D printer hardware over USB and runs on a
Raspberry Pi / Banana Pi, which makes "does this actually work" a
question with three different answers depending on what you're
checking. Here's what each tier covers.

## 1. Unit / integration tests (`pytest`) -- fast, every push

```
pip install -r requirements-dev.txt
pytest tests/ -v
```

Runs the real Flask app (`server.app.test_client()`) through actual
WSGI request/response cycles -- routing, file upload handling, the
job state machine, the OctoPrint API shim, API-key enforcement. The
only thing replaced is the printer itself: `DAVINCI_MINIMOVER_BIN`
points at `tests/fixtures/fake_minimover.py`, a stand-in that
understands the same `-c` / `-p` / `-s` subcommands the real driver
calls (see `tests/conftest.py`). This means the full upload -> convert
-> print pipeline runs end-to-end in CI, just against fake hardware.

**What this catches:** Flask route bugs, job-state races, upload
validation, driver interface mistakes, OctoPrint API shim regressions.

**What this can't catch:** anything about the real `minimover` binary
or the real printer's USB protocol.

## 2. ARM emulation CI (GitHub Actions, `.github/workflows/ci.yml`) -- every push

GitHub-hosted runners are x86_64, so "runs in CI" alone doesn't prove
it runs on a Pi. The `arm-emulation` job uses QEMU
(`uraimo/run-on-arch-action`) to actually run inside `armv7` and
`aarch64` containers -- covering both older Pi/Zero/Banana Pi boards
(armv7) and Pi 4/5 (aarch64) -- and does two things install.sh also
does:

- Clones and **compiles minimover from source** with `make`, on real
  ARM userspace (emulated, but a genuine compile -- not cross-compiled
  on x86 and copied over).
- Creates a venv and **installs Flask**, then imports it and
  byte-compiles `server.py` / `printers/*.py` under that Python.

**What this catches:** ARM-specific build failures in minimover
(missing headers, compiler flags that only break on ARM, etc.) and any
Python/Flask incompatibility with the target architecture.

**What this can't catch:** anything involving systemd, udev, real USB
devices, or WiFi radios -- QEMU user-mode emulation doesn't give you a
running init system or real hardware.

## 3. Manual smoke test on real hardware -- before tagging a release

```
./scripts/smoke-test.sh
```

Run this **on the actual Pi**, after `install.sh` has completed. It
checks the things that only exist once you're on real hardware running
under systemd:

- `davinci-server`, `avahi-daemon`, and `comitup` are active and
  enabled as systemd services
- the `/dev/davinci` udev symlink exists (confirms the udev rule's
  `idVendor` actually matches your printer)
- the HTTP endpoints respond on the real running server (not a test
  client)
- `davinci-reset` is installed

It's read-only and safe to re-run any time. It does **not** attempt an
actual print -- after it passes, upload a `.gcode` file through the
browser UI once to confirm the full physical print path works, since
that's the one thing that needs a printer plugged in and can't be
scripted safely.

## Why three tiers instead of just testing on a real Pi

Contributors and CI don't have a Pi + a da Vinci 1.0 Pro sitting
around. Tiers 1 and 2 catch the overwhelming majority of regressions
automatically on every push with no hardware required; tier 3 is a
short, scripted checklist for whoever actually has the hardware (a
maintainer cutting a release, or a user after their own install) to
run once, rather than a manual walkthrough of `install.sh`'s output
each time.
