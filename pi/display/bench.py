"""Test bench: raw TJC instructions to the display, one per line on stdin; every reply as a JSON line on stdout.
The display service holds the serial port, so it must be stopped first (tools/controller does that, and starts it again).

    python3 -u display/bench.py
    > fill 0,0,240,320,0
    {"cmd": "fill 0,0,240,320,0", "ms": 12, "replies": [{"ok": true}]}

Replies (bkcmd=3): ok, an error code with its name (tjc.ERR), a number (0x71, for "get dim") or a string (0x70).

A line that is JSON, {"batch": [instruction, ...], "id": any}, sends a whole screen at once, pipelined like the display
app does (at most BUDGET commands waiting for their reply), and answers one line:
    {"batch": n, "id": …, "ok": n_ok, "errors": [{"i": index, "cmd": …, "name": …}], "ms": …}
(the desktop controller's Designer redraws the screen this way while you edit)."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serial  # noqa: E402

import link  # noqa: E402
import tjc  # noqa: E402

END = tjc.END
BUDGET = 6     # commands in flight: more overflows the display's input buffer at 921600 (error 0x24)


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


def batch(s, cmds):
    """Send cmds with at most BUDGET unanswered; count the replies (one per command with bkcmd=3)."""
    t0, sent, got, buf, ok, errors = time.time(), 0, 0, b"", 0, []

    def read(wait):
        nonlocal buf, got, ok
        deadline = time.time() + wait
        while True:
            chunk = s.read(256)
            if chunk:
                buf += chunk
                while END in buf:
                    rep, buf = buf.split(END, 1)
                    if not rep:
                        continue
                    if rep[0] == 0x01:
                        ok += 1
                    elif rep[0] not in (0x70, 0x71):
                        errors.append({"i": got, "cmd": cmds[got] if got < len(cmds) else None,
                                       "name": tjc.ERR.get(rep[0], f"code 0x{rep[0]:02X}")})
                    got += 1
                return True
            if time.time() > deadline:
                return False

    s.reset_input_buffer()
    for c in cmds:
        while sent - got >= BUDGET:
            if not read(1.0):            # no reply for a second: carry on (the display may have dropped one)
                got = sent - BUDGET + 1
        s.write(str(c).encode("utf-8") + END)
        sent += 1
    while got < sent and read(0.5):
        pass
    return {"batch": len(cmds), "ok": ok, "errors": errors[:8], "ms": round((time.time() - t0) * 1000)}


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
        if cmd.lstrip().startswith("{"):
            try:
                req = json.loads(cmd)
                out = batch(s, [str(c) for c in req.get("batch") or []])
                out["id"] = req.get("id")
            except (ValueError, TypeError) as e:
                out = {"batch": 0, "error": str(e)}
            print(json.dumps(out), flush=True)
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
