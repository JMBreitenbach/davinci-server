#!/bin/bash -e
#
# Runs inside the image's chroot. Installs davinci-server the same way
# a real user would -- by running install.sh -- just with
# --image-build so it skips the steps that need a live running system
# (starting services, reloading udev). Those take effect on first real
# boot instead, exactly as they would after a normal manual install.

cd /opt/davinci-src
chmod +x install.sh
DAVINCI_USER="$(cat .image-build-user)" DAVINCI_IMAGE_BUILD=1 ./install.sh --image-build

cd /
rm -rf /opt/davinci-src
