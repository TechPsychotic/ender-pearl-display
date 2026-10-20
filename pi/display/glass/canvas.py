"""Drawing surface for the glass UI. The same calls draw on the real display (TjcCanvas: TJC instructions over UART3)
or into a PNG on the laptop (design/pilcanvas.py), so mockups show exactly what the display will draw.

Layers are full-screen pictures of the current wallpaper: "bg" (the image), "glass" (blurred, dark, faint teal) and
"focus" (lighter, more teal). A panel is the same rectangle copied from the glass layer; text is anti-aliased and
blended onto the layer under it (TJC xstr with a cropped picture background)."""
import json
import math
import os

from . import theme as T

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "icons.json")) as _f:
    ICONS = {k: chr(v) for k, v in json.load(_f)["codepoints"].items()}

LEFT, CENTER, RIGHT = 0, 1, 2
TOP, MIDDLE, BOTTOM = 0, 1, 2


class Canvas:
    W, H = T.W, T.H

    # ---- primitives each backend provides ----
    def crop(self, layer, x, y, w, h):          # copy a rectangle of a layer picture to the same place
        raise NotImplementedError

    def fill(self, x, y, w, h, color):
        raise NotImplementedError

    def line(self, x0, y0, x1, y1, color):
        raise NotImplementedError

    def text(self, x, y, w, h, s, font, color, align=LEFT, valign=MIDDLE, on="glass"):
        """on: the layer under the text ("bg"/"glass"/"focus") or an RGB tuple for a solid background."""
        raise NotImplementedError

    def flush(self):
        pass

    def brightness(self, pct):
        pass

    def picture(self, x, y, pid):            # a whole stored picture at (x, y) (boot animation frames)
        raise NotImplementedError

    # ---- shared shapes ----
    def background(self, x=0, y=0, w=T.W, h=T.H):
        if (x, y, w, h) == (0, 0, T.W, T.H) and hasattr(self, "record"):
            self.record = []                   # a full redraw: the recording starts over
        self.crop("bg", x, y, w, h)

    def panel(self, x, y, w, h, focus=False, r=T.RADIUS, edge=True):
        layer = "focus" if focus else "glass"
        self.crop(layer, x, y, w, h)
        for yy in range(min(r, h // 2)):    # rounded corners: the wallpaper back outside the arc (hard edge, like the display)
            dx = r - int(math.sqrt(max(0.0, r * r - (r - yy - 0.5) ** 2)))
            if dx <= 0:
                continue
            for py in (y + yy, y + h - 1 - yy):
                self.crop("bg", x, py, dx, 1)
                self.crop("bg", x + w - dx, py, dx, 1)
        if edge:   # highlight lines stay inside the corner curves (inset r + 3), so nothing sticks out past the round
            ins = r + 3
            self.line(x + ins, y + 1, x + w - ins - 1, y + 1, T.TEAL_EDGE if focus else T.EDGE)          # one pixel inside the edge
            if focus:
                self.line(x + ins, y + h - 2, x + w - ins - 1, y + h - 2, (60, 160, 150))

    def icon(self, x, y, w, h, name, color=T.TEAL_TEXT, font="icon", on="glass", align=CENTER):
        self.text(x, y, w, h, ICONS.get(name, "?"), font, color, align, MIDDLE, on)

    def bar(self, x, y, w, h, frac, color=T.TEAL):
        frac = max(0.0, min(1.0, frac or 0.0))
        done = int(round((w - 1) * frac)) if frac > 0 else 0
        if done:
            self.fill(x, y, done, h, color)
        if done < w:
            self.fill(x + done, y, w - done, h, T.TRACK)


class TjcCanvas(Canvas):
    """The real display. pics: {"bg": id, "glass": id, "focus": id} of the current wallpaper; fonts: role -> TJC id.
    Every command waits for the display's 0x01 (bkcmd=3) once the in-flight budget is used, so the display's serial
    buffer never overflows (at 921600 baud blasting commands gave 0x24 overflow errors)."""

    def __init__(self, ser, pics, fonts, budget=6):
        self.ser, self.pics, self.fonts, self.budget, self.inflight, self.errors = ser, pics, fonts, budget, 0, []
        self.record, self.record_v = [], 0     # commands since the last full redraw (the web UI replays them as a live preview)

    def _send(self, cmd):
        self.record.append(cmd); self.record_v += 1
        data = cmd.encode("utf-8") + b"\xff\xff\xff"
        if self.inflight >= self.budget:
            self._wait(self.inflight - self.budget + 1)
        self.ser.write(data)
        self.inflight += 1

    def _wait(self, n):
        got = 0
        buf = b""
        while got < n:
            chunk = self.ser.read(4)
            if not chunk:
                self.inflight = 0   # timed out: the display may have dropped replies; start over
                return
            buf += chunk
            while b"\xff\xff\xff" in buf:
                rep, buf = buf.split(b"\xff\xff\xff", 1)
                if rep and rep[0] != 0x01:
                    self.errors.append(rep[0])
                got += 1
                self.inflight -= 1

    def flush(self):
        if self.inflight:
            self._wait(self.inflight)

    def brightness(self, pct):
        self._send(f"dim={max(0, min(100, int(pct)))}")

    @staticmethod
    def c(color):
        return T.rgb(*color) if isinstance(color, (tuple, list)) else int(color)   # lists come from JSON

    def crop(self, layer, x, y, w, h):
        if w > 0 and h > 0:
            self._send(f"xpic {x},{y},{w},{h},{x},{y},{self.pics[layer]}")

    def picture(self, x, y, pid):
        self._send(f"pic {x},{y},{pid}")

    def fill(self, x, y, w, h, color):
        if w > 0 and h > 0:
            self._send(f"fill {x},{y},{w},{h},{self.c(color)}")

    def line(self, x0, y0, x1, y1, color):
        self._send(f"line {x0},{y0},{x1},{y1},{self.c(color)}")

    def text(self, x, y, w, h, s, font, color, align=LEFT, valign=MIDDLE, on="glass"):
        s = "".join(ch if ch >= " " and ch not in '"\\' else "'" for ch in str(s))
        if isinstance(on, (tuple, list)):
            sta, back = 1, self.c(on)
        else:
            sta, back = 0, self.pics[on]          # crop: the background comes from that picture (smooth blending)
        self._send(f'xstr {x},{y},{w},{h},{self.fonts[font]},{self.c(color)},{back},{align},{valign},{sta},"{s}"')
