# Pre-built Raspberry Pi image

This directory holds the [pi-gen](https://github.com/RPi-Distro/pi-gen)
stage that `.github/workflows/pi-image.yml` uses to build a ready-to-flash
Raspberry Pi OS Lite (64-bit) image with davinci-server already installed.
It doesn't vendor pi-gen itself -- the workflow clones
`RPi-Distro/pi-gen` fresh on each build and drops these files into it.

## How it fits together

1. `config` -- pi-gen build settings: Raspberry Pi OS Lite (64-bit,
   currently Trixie -- see the comment in `config`), headless
   (`STAGE_LIST` skips the desktop stages), no baked-in
   username/password/WiFi/SSH (see below).
2. `stage-davinci/00-davinci/00-run.sh` -- runs on the host (not
   chrooted). Copies a davinci-server checkout -- staged into
   `files/davinci-server` by the workflow just before the pi-gen build
   starts -- into the image's rootfs at `/opt/davinci-src`, plus a
   one-line file recording which user account to install for.
3. `stage-davinci/00-davinci/01-run-chroot.sh` -- runs inside the
   image's chroot. Runs `install.sh --image-build` from that copy,
   then deletes it. This is the same `install.sh` a manual install
   uses -- see its `--image-build` / `DAVINCI_IMAGE_BUILD=1` mode,
   which skips the two things that need a live running system
   (starting services, `udevadm trigger`) since neither exists in a
   chroot. Everything else -- packages, building `minimover`, the
   systemd unit, the udev rule, comitup config -- is identical to a
   real install and takes effect on first real boot.

Reusing `install.sh` instead of re-declaring comitup/systemd config
directly in the pi-gen stage was a deliberate choice: it keeps one
source of truth, so the image can't drift out of sync with what a
manual install does.

## No baked-in credentials

`config` intentionally leaves `FIRST_USER_NAME`, `FIRST_USER_PASS`,
WiFi, and SSH unset. Buyers set all of that themselves through
Raspberry Pi Imager's "Edit Settings" (gear icon) before flashing --
exactly like a stock Raspberry Pi OS image. Baking a default
password into every image would ship the same known credentials on
every board built.

## Known limitation: renaming the default user via Imager

pi-gen's default account (`pi`, via `FIRST_USER_NAME`) is what
`install.sh --image-build` installs the systemd service and udev rule
for. If a buyer uses Raspberry Pi Imager to set a **different**
username, Imager's first-boot process renames that existing account
(`usermod`) rather than creating a new one -- which would leave the
`davinci-server.service` unit's `User=pi` referencing a username that
no longer exists. This isn't handled yet. If it turns out to be a
common case, the fix would be to have `install.sh` run the service as
a dedicated system account instead of a personal login user, but that
changes install.sh's behavior for regular manual installs too, so
it's deliberately out of scope here rather than folded in silently.

## Build/release automation

`.github/workflows/pi-image.yml` builds via pi-gen's own
`build-docker.sh` (a privileged container handles the loop-device/
chroot work pi-gen needs) on standard `ubuntu-latest` GitHub-hosted
runners -- no self-hosted runner or cloud VM. This repo is public, so
those Actions minutes are free.

It's checked on a monthly cron but only actually builds if it's been
roughly 60 days since the last image release *and* Raspberry Pi OS
has published a newer Lite (64-bit) base image since then -- see the
`check` job. `workflow_dispatch` can force a build on demand
regardless of both checks.

Releases are tagged `pi-image-YYYY-MM-DD`; the `prune-old-releases`
job keeps only the 3 most recent, deleting older ones (and their
tags). This only ever touches `pi-image-*` releases -- any future
non-image release (e.g. a tagged code release) is left alone.

## What isn't covered yet

- No automated boot/smoke test of the built image (e.g. via QEMU).
  The image is built and released untested beyond pi-gen's own build
  succeeding. Worth adding later if this image sees real use.
- The udev rule's USB vendor ID is still the same unconfirmed default
  `install.sh` has always shipped (see its output) -- baking the image
  doesn't change that caveat.
