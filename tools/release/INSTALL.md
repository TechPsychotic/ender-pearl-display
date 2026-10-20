# Ender Pearl Display: install

This package holds everything needed to put the Ender Pearl firmware on an Ender-3 V3 SE display and run the UI from a
Raspberry Pi 4. The full write-up is in `docs/` (start with `docs/README.md`).

## Contents
| Path | |
|---|---|
| `firmware/glass.tft` | the display firmware (TJC3224T132_011N only) |
| `pi/display/` | the Pi app, the serial flasher, the knob driver |
| `server/` | the systemd user service + installer, and the display's web API (reference) |
| `docs/` | hardware, pinout, protocols, firmware, drawing, Pi software, troubleshooting |
| `tests/` | unit tests (no hardware needed) |

## Steps
1. **Wire** the display to the Pi, with the printer off: `docs/01-hardware.md`.
2. **Enable UART3** on the Pi: add `dtoverlay=uart3` to `/boot/firmware/config.txt`, then reboot.
3. `pip install pyserial` (or `sudo apt install python3-serial`).
4. **Probe**, which writes nothing: `python3 pi/display/flash.py --probe`. Expect `comok … TJC3224T132_011N …`.
5. **Keep a way back:** download Creality's display firmware (link and sha256 in `docs/03-custom-firmware.md`,
   "Back to stock").
6. **Flash:** `python3 pi/display/flash.py firmware/glass.tft`. It runs at 921600 baud (under a minute for the 1.8 MB file), and the
   display restarts into the boot animation.
7. **Run the UI:** `python3 pi/display/glass_main.py`. It needs the Ender Pearl web API on `127.0.0.1:8080`
   (`docs/05-pi-software.md` lists the calls; adapt `glass_main.Api` for another host). As a service:
   `server/install_display.sh`.

Back to stock: `python3 pi/display/flash.py --stock`, or Creality's `TJC_SET` folder on a microSD card in the
display's own slot.

Licence: GPL-3.0 (`LICENSE`); fonts and icons under their own licences (`licenses/`).
