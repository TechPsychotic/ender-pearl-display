"""Listen-only logger for the printer → display traffic (DISPLAY_RE.md step 2): maps what the stock firmware draws on
*our* display firmware (icon libraries and ids differ between display firmware versions).

Wiring for listening: the Pi's RXD3 (pin 29, GPIO5) on the line that goes from the mainboard to the display's RX pin,
and a Pi GND to the printer's GND. Nothing else: the Pi only listens, the printer and display work as normal.
The mainboard's TX is 3.3 V logic (STM32-class MCU), safe for the Pi; measure it first anyway (DISPLAY_RE.md).

    python3 display/sniff.py                 # UART3, 115200, decoded frames
    python3 display/sniff.py --raw --out out/display_sniff.log
Ctrl+C prints a summary: every icon (library, id) seen and where."""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serial  # noqa: E402

import link  # noqa: E402
import protocol as D  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--baud", type=int, default=link.BAUD)
    ap.add_argument("--raw", action="store_true", help="also print the raw bytes of every frame")
    ap.add_argument("--out", help="append everything to this log file")
    a = ap.parse_args()
    port = a.port or link.find_port()
    if not port:
        sys.exit("no UART3: add dtoverlay=uart3 to /boot/firmware/config.txt and reboot")
    ser = serial.Serial(port, a.baud, timeout=0.05)
    log = open(a.out, "a") if a.out else None
    say = lambda s: (print(s, flush=True), log and (log.write(s + "\n"), log.flush()))
    say(f"# listening on {port} at {a.baud} baud, {time.strftime('%Y-%m-%d %H:%M:%S')}")
    t0, buf, icons, frames, junk = time.time(), b"", {}, 0, 0
    try:
        while True:
            data = ser.read(512)
            if not data:
                continue
            buf += data
            got, rest = D.parse(buf)
            junk += len(buf) - len(rest) - sum(len(p) + 6 for _, p in got)
            buf = rest[-4096:]
            for cmd, payload in got:
                frames += 1
                line = f"{time.time() - t0:9.3f}  {D.describe(cmd, payload)}"
                if a.raw:
                    line += "   | " + (bytes([0xAA, cmd]) + payload).hex(" ")
                say(line)
                if cmd == 0x97 and len(payload) == 8:
                    k = (payload[4], int.from_bytes(payload[6:8], "big"))
                    icons.setdefault(k, set()).add((int.from_bytes(payload[0:2], "big"), int.from_bytes(payload[2:4], "big")))
            if junk > 200 and frames == 0:
                say(f"# {junk} bytes and no frames: wrong baud rate or wrong line? (try --baud 125000)")
                junk = 0
    except KeyboardInterrupt:
        pass
    say(f"# {frames} frames, {junk} stray bytes")
    for (lib, iid), where in sorted(icons.items()):
        say(f"# icon lib {lib:2d} id {iid:3d} at " + ", ".join(f"({x},{y})" for x, y in sorted(where)))


if __name__ == "__main__":
    main()
