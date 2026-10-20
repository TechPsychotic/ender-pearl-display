"""Frame builder for the Ender-3 V3 SE's TJC3224 display (DWIN-T5L-like protocol). Untested on hardware yet:
encodings follow the byte sequences logged in jpcurti/E3V3SE_display_klipper docs/tjc3224_reverse_engineering.md.
See DISPLAY_RE.md for the plan. Frames: AA <cmd> <payload> CC 33 C3 3C, numbers big-endian 16-bit."""
import struct

HEAD, TAIL = b"\xAA", b"\xCC\x33\xC3\x3C"
W, H = 240, 320          # portrait in the logged coordinates (x up to 0xEF, y up to 0x13F)


def frame(cmd, payload=b""):
    return HEAD + bytes([cmd]) + payload + TAIL


def u16(*vals):
    return b"".join(struct.pack(">H", int(v) & 0xFFFF) for v in vals)


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def handshake():
    return frame(0x00)


def colors(fg, bg=0xFFFF):
    """AA 40 <fg> <bg>: e.g. colors(0xFFFF, 0xFFFF) = white (logged 'AA 40 FF FF FF FF')."""
    return frame(0x40, u16(fg, bg))


def fill_rect(x0, y0, x1, y1):
    _check(x0, y0, x1, y1)
    return frame(0x5B, u16(x0, y0, x1, y1))


def rect(x0, y0, x1, y1):
    _check(x0, y0, x1, y1)
    return frame(0x59, u16(x0, y0, x1, y1))


def icon(x, y, lib_flags, icon_id):
    """AA 97 <x> <y> <lib/flags> <icon>. lib_flags as logged, e.g. 0x0600 for English text icons,
    0x0201 for the main-menu tiles, 0x1B01 for the boot animation."""
    return frame(0x97, u16(x, y, lib_flags, icon_id))


def scroll(direction_up, dy, color, x0, y0, x1, y1):
    """AA 09 82|83 <dy> <colour> <x0> <y0> <x1> <y1>: move a region up (0x82) or down (0x83)."""
    return frame(0x09, bytes([0x82 if direction_up else 0x83]) + u16(dy, color, x0, y0, x1, y1))


def _check(x0, y0, x1, y1):
    if not (0 <= x0 <= x1 < W and 0 <= y0 <= y1 < H):
        raise ValueError(f"rectangle {x0},{y0}-{x1},{y1} is outside {W}x{H}")


# ---- 2026-10-18: the rest of the command set, from jpcurti's working TJC3224 driver (E3V3SE_display_klipper,
# TJC3224.py; GPL-3.0, so only the byte layouts are taken, not code). The first colour of colors() is the drawing
# (foreground) colour used by lines, rectangles and fills; the second is the background used by clear().
CMD_NAMES = {0x00: "handshake", 0x09: "move-area", 0x14: "number", 0x3D: "boot?", 0x40: "colors", 0x51: "line/point",
             0x52: "clear", 0x59: "rect", 0x5B: "fill-rect", 0x5C: "invert-rect", 0x5F: "backlight",
             0x70: "picture", 0x97: "icon", 0x98: "text"}
FONTS = {"8x8": 0, "6x12": 1, "8x16": 2, "12x24": 3, "16x32": 4, "20x40": 5, "24x48": 6, "28x56": 7, "32x64": 8}
FONT_PX = {0: (8, 8), 1: (6, 12), 2: (8, 16), 3: (12, 24), 4: (16, 32), 5: (20, 40), 6: (24, 48), 7: (28, 56), 8: (32, 64)}
WHITE, BLACK = 0xFFFF, 0x0000


def clear(color=BLACK):
    """Fill the whole screen with color: AA 40 <fg> <bg=color>, then AA 52."""
    return colors(WHITE, color) + frame(0x52)


def line(x0, y0, x1, y1):
    """Line in the current drawing colour: AA 51 <x0> <y0> <x1> <y1>."""
    _check(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    return frame(0x51, u16(x0, y0, x1, y1))


def point(x, y):
    _check(x, y, x, y)
    return frame(0x51, u16(x, y))


def invert_rect(x0, y0, x1, y1):
    """Invert the colours of an area (menu highlight): AA 5C <x0> <y0> <x1> <y1>."""
    _check(x0, y0, x1, y1)
    return frame(0x5C, u16(x0, y0, x1, y1))


def backlight(level):
    """Backlight 0 (off) … 64 (full): AA 5F <level>."""
    return frame(0x5F, bytes([max(0, min(64, int(level)))]))


def text(x, y, s, size=FONTS["8x16"], fg=WHITE, bg=BLACK, show_bg=True):
    """Text in the display's built-in font: AA 98 <x> <y> 00 <mode> <size> <fg> <bg> <bytes>.
    mode 0x02 (+0x40 = paint the background box). ASCII only (other bytes depend on the display's font)."""
    _check(x, y, x, y)
    data = s.encode("ascii", "replace")
    if b"\xCC\x33\xC3\x3C" in data:
        raise ValueError("text contains the frame tail")
    return frame(0x98, u16(x, y) + bytes([0x00, 0x02 | (0x40 if show_bg else 0), size]) + u16(fg, bg) + data)


def icon_lib(x, y, lib, icon_id, show_bg=False):
    """icon() with library and background flag as separate values: lib 0 icons, 27 boot animation, text libraries per
    language (which number is which depends on the display firmware: map ours first)."""
    return icon(x, y, (lib << 8) | (1 if show_bg else 0), icon_id)


def picture(pid=1):
    """Show a full-screen picture stored in the display: AA 70 <id>."""
    return frame(0x70, bytes([pid & 0xFF]))


def text_width(s, size=FONTS["8x16"]):
    return len(s) * FONT_PX[size][0]


def parse(buf):
    """Split a byte stream into frames. Returns (frames, rest): each frame is (cmd, payload); bytes that don't
    start with AA are skipped (line noise, a wrong baud rate); an unfinished frame stays in rest."""
    out, i = [], 0
    while True:
        s = buf.find(HEAD, i)
        if s < 0:
            return out, b""
        e = buf.find(TAIL, s + 1)
        if e < 0:
            return out, buf[s:]
        body = buf[s + 1:e]
        if body:
            out.append((body[0], bytes(body[1:])))
        i = e + len(TAIL)


def describe(cmd, payload):
    """One readable line for a frame (used by sniff.py)."""
    n = CMD_NAMES.get(cmd, f"cmd {cmd:02X}")
    w = [int.from_bytes(payload[k:k + 2], "big") for k in range(0, len(payload) - 1, 2)]
    if cmd == 0x40 and len(w) >= 2:
        return f"{n} fg={w[0]:04X} bg={w[1]:04X}"
    if cmd in (0x59, 0x5B, 0x5C, 0x51) and len(payload) in (4, 8):
        return f"{n} " + " ".join(map(str, w))
    if cmd == 0x97 and len(payload) == 8:
        return f"{n} x={w[0]} y={w[1]} lib={payload[4]} bg={payload[5]} id={w[3]}"
    if cmd == 0x98 and len(payload) >= 11:
        return f"{n} x={w[0]} y={w[1]} size={payload[6]} fg={int.from_bytes(payload[7:9], 'big'):04X} {payload[11:]!r}"
    if cmd == 0x00 and payload[:2] == b"OK":
        return "handshake reply OK"
    return f"{n} {payload.hex(' ')}".rstrip()


def is_handshake_reply(buf):
    """The display answers the handshake with AA 00 'O' 'K' …"""
    return any(c == 0x00 and p[:2] == b"OK" for c, p in parse(buf)[0]) or b"\xAA\x00OK" in buf
