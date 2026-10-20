"""Exact character advance widths of our TJC fonts, read from the generated .zi files -> glass/metrics.json.
The display wraps text that is wider than its box, so the app fits and scrolls text with these real widths.
.zi layout used: u32 glyph count at 0x0C; a table of 10-byte entries (u16 code, u8 advance width, ...)."""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from glass import theme as T
FONTS = os.path.join(os.path.dirname(HERE), "fonts")
out = {}
for i, role in enumerate(T.FONT_ORDER):
    h = T.FONTS[role][0]
    path = os.path.join(FONTS, f"f{i}_{role}{h}.zi")
    d = open(path, "rb").read()
    n = struct.unpack_from("<I", d, 0x0C)[0]
    chars = T.FONTS[role][2]
    def ok(s0):   # n entries, 10 bytes apart, codes strictly increasing, widths plausible, only the font's characters
        prev = -1
        for k in range(n):
            code, w = struct.unpack_from("<HB", d, s0 + 10 * k)
            if code <= prev or w > 3 * h or (chars and chr(code) not in chars):
                return False
            prev = code
        return True
    start = next(s0 for s0 in range(0x20, 0x200) if ok(s0))
    widths = {}
    for k in range(n):
        code, w = struct.unpack_from("<HB", d, start + 10 * k)
        widths[chr(code)] = w
    out[role] = {"height": h, "widths": widths}
    print(f"{role:7s} h{h:3d} {len(widths):3d} glyphs  e.g. 'M'={widths.get('M')} 'i'={widths.get('i')} ' '={widths.get(' ')}")
json.dump(out, open(os.path.join(HERE, "glass", "metrics.json"), "w"))
