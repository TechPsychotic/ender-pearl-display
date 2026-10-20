#!/bin/bash
# Build the release assets in dist/: the install zip and a copy of the firmware image.
#   tools/release/make_release.sh v1.0.0
set -euo pipefail
ver=${1:?version, e.g. v1.0.0}
cd "$(dirname "$0")/../.."
name="ender-pearl-display-$ver"
rm -rf dist && mkdir -p "dist/$name"
cp -r firmware pi server docs tests licenses LICENSE README.md "dist/$name/"
cp tools/release/INSTALL.md "dist/$name/"
rm -f "dist/$name/firmware/glass.hmi"                 # the editor project stays in the repo
mkdir -p "dist/$name/pi/display/glass/assets"         # the web UI's live screen preview reads these
cp design/assets/*.png "dist/$name/pi/display/glass/assets/"
find "dist/$name" -name __pycache__ -prune -exec rm -rf {} +
(cd dist && zip -qr "$name.zip" "$name")
cp firmware/glass.tft "dist/ender-pearl-glass-$ver.tft"
cp docs/images/banner.png "dist/ender-pearl-display-banner.png"
(cd dist && sha256sum "$name.zip" "ender-pearl-glass-$ver.tft" > SHA256SUMS)
rm -rf "dist/$name"
ls -la dist && cat dist/SHA256SUMS
