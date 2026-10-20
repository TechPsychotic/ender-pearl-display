#!/bin/bash
# Start the printer-display UI at boot (systemd user service, like ender-loop; no sudo needed).
#   bash ~/closedloop/tools/server/install_display.sh
# Needs dtoverlay=uart3 in /boot/firmware/config.txt and the display wired as in DISPLAY_RE.md.
# Afterwards:  systemctl --user restart ender-loop-display   ·   tail -f ~/closedloop/out/display.log
set -e
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p ~/.config/systemd/user ~/closedloop/out
install -m 644 "$here/ender-loop-display.service" ~/.config/systemd/user/ender-loop-display.service
pkill -f "^/usr/bin/python3 -u display/(demo|ui|glass_main).py" || true      # a hand-started copy would hold the UART and knob pins
systemctl --user stop ender-pearl-display-test ender-loop-display-test 2>/dev/null || true
systemctl --user daemon-reload
systemctl --user enable --now ender-loop-display.service
sleep 2
systemctl --user --no-pager status ender-loop-display.service | head -5
