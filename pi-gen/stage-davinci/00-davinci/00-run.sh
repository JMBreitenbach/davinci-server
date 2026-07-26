#!/bin/bash -e
#
# Host-side (not chrooted): copies the davinci-server checkout staged
# into files/davinci-server by the calling workflow into the rootfs,
# along with a record of which user account install.sh should target.
# See 01-run-chroot.sh for the part that actually runs install.sh.

if [ ! -d files/davinci-server ]; then
  echo "ERROR: files/davinci-server is missing -- the calling workflow" >&2
  echo "should have populated it from a davinci-server checkout before" >&2
  echo "running pi-gen. See pi-gen/README.md." >&2
  exit 1
fi

cp -r files/davinci-server "${ROOTFS_DIR}/opt/davinci-src"

# FIRST_USER_NAME comes from pi-gen's config (sourced by pi-gen itself
# before running any stage script) -- write it to a file rather than
# relying on it being exported into 01-run-chroot.sh's environment.
echo "${FIRST_USER_NAME:-pi}" > "${ROOTFS_DIR}/opt/davinci-src/.image-build-user"
