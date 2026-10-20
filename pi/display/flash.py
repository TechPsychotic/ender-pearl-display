"""Flash a TJC .tft to the printer display over UART3 (no SD card). DISPLAY_RE.md plan C2.

    python3 display/flash.py path/to/file.tft            # our firmware
    python3 display/flash.py --stock                     # back to Creality's (out/stock_display_fw/TJC_SET/tjc.tft)
    python3 display/flash.py --probe                     # only ask the display who it is ("comok ..."), writes nothing

The display answers TJC's upload handshake even while running Creality's firmware (checked 2026-10-18:
"comok 0,30599-0,TJC3224T132_011N,37,61760,…,8388608" = model TJC3224T132_011N, 8 MB flash).
If an upload is interrupted, run it again (the bootloader is not touched); the microSD card in the display's slot
(TJC_SET folder) is the fallback. The display UI service is stopped while flashing and started again afterwards."""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serial  # noqa: E402

import link  # noqa: E402
import tjc  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK = os.path.join(ROOT, "out", "stock_display_fw", "TJC_SET", "tjc.tft")
MODEL_FAMILY = "TJC3224T132_011"
UNITS = ("ender-loop-display-test", "ender-loop-display")


def probe(ser):
    ser.reset_input_buffer()
    ser.write(tjc.END + tjc.SYNC + tjc.END + tjc.cmd("connect"))
    time.sleep(0.6)
    r = ser.read(300)
    for chunk in r.split(tjc.END):   # replies of our firmware (e.g. a stray 0x1A) can come before it
        if b"comok" in chunk:
            return chunk[chunk.index(b"comok"):].decode(errors="replace")
    return None


def services(action):
    for u in UNITS:
        subprocess.run(["systemctl", "--user", action, u], capture_output=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tft", nargs="?")
    ap.add_argument("--stock", action="store_true", help="flash Creality's original display firmware")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--baud", type=int, default=115200, help="display's current baud (115200 for Creality's firmware)")
    ap.add_argument("--upload-baud", type=int, default=921600)
    a = ap.parse_args()
    path = STOCK if a.stock else a.tft
    if not a.probe and not (path and os.path.isfile(path)):
        sys.exit("give a .tft file, --stock or --probe")
    was_active = [u for u in UNITS if subprocess.run(["systemctl", "--user", "is-active", "--quiet", u]).returncode == 0]
    services("stop")
    try:
        ser = serial.Serial(link.find_port(), a.baud, timeout=0.5)
        info = probe(ser)
        if not info:
            sys.exit(f"no 'comok' at {a.baud} baud: try --baud 9600 or 921600 (our firmware's setting), check the wiring")
        print("display:", info)
        if MODEL_FAMILY not in info:
            sys.exit(f"unexpected model (want {MODEL_FAMILY}*): not flashing")
        if a.probe:
            return
        print(f"flashing {path} ({os.path.getsize(path)} bytes) at {a.upload_baud} baud ...")
        t0 = time.time()
        tjc.upload(ser, path, a.upload_baud)
        print(f"done in {time.time() - t0:.0f} s")
        ser.close()
    finally:
        time.sleep(3)   # the display restarts with the new firmware
        for u in was_active:
            subprocess.run(["systemctl", "--user", "start", u], capture_output=True)


if __name__ == "__main__":
    main()
