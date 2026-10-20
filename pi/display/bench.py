"""Test bench: raw TJC instructions to the display, one per line on stdin; every reply as a JSON line on stdout.
The display service holds the serial port, so it must be stopped first (tools/controller does that, and starts it again).

    python3 -u display/bench.py
    > fill 0,0,240,320,0
    {"cmd": "fill 0,0,240,320,0", "ms": 12, "replies": [{"ok": true}]}

Replies (bkcmd=3): ok, an error code with its name (tjc.ERR), a number (0x71, for "get dim") or a string (0x70)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serial  # noqa: E402

import link  # noqa: E402
import tjc  # noqa: E402

END = tjc.END


def open_link(port):
    for baud in (921600, 115200):   # 921600 after the display app ran, 115200 after power-up
        s = serial.Serial(port, baud, timeout=0.05)
        s.write(END + b"get dim" + END)
        time.sleep(0.15)
        if b"\x71" in s.read(64):
            s.write(b"bkcmd=3" + END)
            time.sleep(0.05)
            s.reset_input_buffer()
            return s
        s.close()
    return None


def decode(rep):
    if not rep:
        return None
    code = rep[0]
    if code == 0x01:
        return {"ok": True}
    if code == 0x71 and len(rep) >= 5:
        return {"number": int.from_bytes(rep[1:5], "little", signed=True)}
    if code == 0x70:
        return {"string": rep[1:].decode("utf-8", "replace")}
    return {"error": code, "name": tjc.ERR.get(code, f"code 0x{code:02X}")}


def main():
    port = link.find_port()
    s = open_link(port) if port else None
    print(json.dumps({"ready": bool(s), "port": port, "baud": s.baudrate if s else None}), flush=True)
    if not s:
        return
    for line in sys.stdin:
        cmd = line.rstrip("\r\n")
        if not cmd.strip():
            continue
        s.reset_input_buffer()
        t0 = time.time()
        s.write(cmd.encode("utf-8") + END)
        if cmd.startswith("baud="):          # the display switches right after its reply
            time.sleep(0.1)
            s.baudrate = int(cmd.split("=", 1)[1])
        buf, deadline = b"", time.time() + 0.6
        while time.time() < deadline:
            chunk = s.read(256)
            if chunk:
                buf += chunk
                deadline = min(deadline, time.time() + 0.08)   # a little longer for more replies, then done
        reps = [decode(r) for r in buf.split(END) if r]
        print(json.dumps({"cmd": cmd, "ms": round((time.time() - t0) * 1000), "replies": [r for r in reps if r]}), flush=True)


if __name__ == "__main__":
    main()
