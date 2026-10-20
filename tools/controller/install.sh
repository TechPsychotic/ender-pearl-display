#!/bin/bash
# Add "Ender Pearl Display" to the desktop's app list (GNOME / any freedesktop desktop), for this user.
set -e
here="$(cd "$(dirname "$0")" && pwd)"
id=io.github.techpsychotic.EnderPearlController
mkdir -p ~/.local/share/applications ~/.local/share/icons/hicolor/512x512/apps
install -m 644 "$here/../../docs/images/logo.png" ~/.local/share/icons/hicolor/512x512/apps/$id.png
cat > ~/.local/share/applications/$id.desktop <<DESK
[Desktop Entry]
Type=Application
Name=Ender Pearl Display
Comment=Control, flash and test the Ender-3 V3 SE display through the Pi
Exec=python3 "$here/ender_pearl_controller.py"
Icon=$id
Categories=Utility;
StartupWMClass=$id
DESK
update-desktop-database ~/.local/share/applications 2>/dev/null || true
echo "installed: Ender Pearl Display (app list), runs $here/ender_pearl_controller.py"
