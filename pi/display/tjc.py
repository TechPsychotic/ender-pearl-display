"""TJC (Nextion-compatible) standard instruction set, for the display running *our* firmware (DISPLAY_RE.md plan C2).

Our .tft holds only resources (fonts, pictures, one blank page); the Pi draws everything with these commands.
Every command is ASCII text ended by FF FF FF. With bkcmd=3 the display answers 0x01 (ok) or an error code
(0x02 bad component, 0x1A bad variable, 0x1E bad parameters, 0x24 buffer overflow …) to every command.

Coordinates: our project is portrait 240 x 320 (x 0–239, y 0–319). Colours: RGB565 numbers, as in protocol.rgb565.
Fonts and pictures are referred to by their index in the project (see display/assets/manifest.json).

Upload (flash a .tft over the serial line, no SD card): Nextion/TJC upload protocol, see upload()."""
import os
import time

END = b"\xff\xff\xff"
ERR = {0x00: "invalid instruction", 0x02: "invalid component", 0x03: "invalid page", 0x04: "invalid picture",
       0x05: "invalid font", 0x11: "invalid baud", 0x1A: "invalid variable", 0x1B: "invalid operation",
       0x1E: "invalid parameter count", 0x1F: "IO failed", 0x20: "escape character", 0x23: "variable name too long",
       0x24: "serial buffer overflow"}
# xstr alignment / background
LEFT, CENTER, RIGHT = 0, 1, 2
TOP, MIDDLE, BOTTOM = 0, 1, 2
BG_CROP, BG_COLOR, BG_IMAGE, BG_NONE = 0, 1, 2, 3


def quote(s):
    """Text for a TJC string literal: no quotes or control characters (the parser has no escapes for them)."""
    return "".join(ch if ch >= " " and ch not in '"\\' else "'" if ch == '"' else " " for ch in str(s))


def cmd(text):
    return text.encode("utf-8") + END


# ---- drawing (all take effect immediately, outside of any component) ----
def cls(color):
    return cmd(f"cls {int(color)}")


def fill(x, y, w, h, color):
    return cmd(f"fill {int(x)},{int(y)},{int(w)},{int(h)},{int(color)}")


def line(x0, y0, x1, y1, color):
    return cmd(f"line {int(x0)},{int(y0)},{int(x1)},{int(y1)},{int(color)}")


def rect(x0, y0, x1, y1, color):
    return cmd(f"draw {int(x0)},{int(y0)},{int(x1)},{int(y1)},{int(color)}")


def circle(x, y, r, color, filled=False):
    return cmd(f"{'cirs' if filled else 'cir'} {int(x)},{int(y)},{int(r)},{int(color)}")


def pic(x, y, pid):
    """Draw picture pid with its top-left at (x, y)."""
    return cmd(f"pic {int(x)},{int(y)},{int(pid)}")


def xpic(x, y, w, h, sx, sy, pid):
    """Draw the w x h part of picture pid that starts at (sx, sy), at (x, y): sprites, highlight frames, gauges."""
    return cmd(f"xpic {int(x)},{int(y)},{int(w)},{int(h)},{int(sx)},{int(sy)},{int(pid)}")


def text(x, y, w, h, s, font, color, bg=0, align=LEFT, valign=MIDDLE, bgmode=BG_NONE):
    """xstr: text in project font `font` inside the box (x, y, w, h). bgmode BG_NONE draws only the glyphs
    (anti-aliased fonts blend with what is already there); BG_COLOR fills the box with bg first."""
    return cmd(f'xstr {int(x)},{int(y)},{int(w)},{int(h)},{int(font)},{int(color)},{int(bg)},{align},{valign},{bgmode},"{quote(s)}"')


# ---- system ----
def page(n=0):
    return cmd(f"page {int(n)}")


def brightness(pct):
    return cmd(f"dim={max(0, min(100, int(pct)))}")


def baud(rate):
    return cmd(f"baud={int(rate)}")


def replies(on=True):
    return cmd(f"bkcmd={3 if on else 0}")


def refresh_off(on=False):
    """ref_stop / ref_star: pause screen updates while drawing a frame, then show it at once (less flicker)."""
    return cmd("ref_star" if on else "ref_stop")


def parse_replies(buf):
    """Split the display's answers (each ends with FF FF FF) into (code, data) tuples."""
    out = []
    for chunk in buf.split(END)[:-1]:
        if chunk:
            out.append((chunk[0], chunk[1:]))
    return out


# ---- flashing a .tft over the serial line (Nextion/TJC upload protocol) ----
SYNC = b"DRAKJHSUYDGBNCJHGJKSHBDN"   # also leaves "protocol reparse" mode (recmod=1), which Creality's firmware may use


def upload(ser, path, upload_baud=115200, log=print):
    """Flash the .tft at path. ser: an open pyserial port at the display's current baud.
    The display answers 'comok …' to connect, then 0x05 after the header and after every 4096-byte block.
    Interrupted uploads are recovered by uploading again (or from the SD card): the bootloader is not touched."""
    size = os.path.getsize(path)
    ser.reset_input_buffer()
    ser.write(cmd("") + SYNC + END + cmd("connect"))
    time.sleep(0.5)
    hello = ser.read(200)
    if b"comok" not in hello:
        raise RuntimeError(f"no 'comok' from the display (got {hello[:60]!r}): is it running a TJC project and at this baud?")
    log("display: " + next(c for c in hello.split(END) if b"comok" in c).decode(errors="replace"))
    ser.write(cmd(f"whmi-wri {size},{upload_baud},0"))
    if upload_baud != ser.baudrate:
        time.sleep(0.05)
        ser.baudrate = upload_baud
    ack = ser.read(1) or (time.sleep(0.5), ser.read(1))[1]
    if ack != b"\x05":
        raise RuntimeError(f"display didn't accept the upload (got {ack!r})")
    sent = 0
    with open(path, "rb") as f:
        while True:
            block = f.read(4096)
            if not block:
                break
            ser.write(block)
            sent += len(block)
            deadline = time.time() + 5
            while ser.read(1) != b"\x05":
                if time.time() > deadline:
                    raise RuntimeError(f"no acknowledgement after {sent} of {size} bytes")
            if sent % (64 * 4096) < 4096:
                log(f"  {sent * 100 // size}%")
    log("upload done: the display restarts with the new firmware")
