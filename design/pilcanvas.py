"""Laptop canvas for the glass UI: the same drawing calls as the display, into a Pillow image (mockups, previews).
Fonts: a TJC font of height h is rendered with the TTF at about h / 1.21 px (Inter's line height); icons at ~0.8 h."""
import json
import os

from PIL import Image, ImageDraw, ImageFont

from glass import theme as T
from glass.canvas import Canvas

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
FONTDIR = "/usr/share/fonts/rsms-inter-fonts"
LUCIDE = os.path.join(HERE, "icons", "epicons.ttf")   # Lucide outlines on ordinary characters


class PilCanvas(Canvas):
    def __init__(self, manifest=None):
        self.manifest = manifest or json.load(open(os.path.join(ASSETS, "manifest.json")))
        self.img = Image.new("RGB", (T.W, T.H))
        self.d = ImageDraw.Draw(self.img)
        self._pics, self._layers, self._fonts = None, {}, {}

    # the app sets .pics = {"bg": id, "glass": id, "focus": id}
    @property
    def pics(self):
        return self._pics

    @pics.setter
    def pics(self, ids):
        self._pics = ids
        self._layers = {k: Image.open(os.path.join(ASSETS, self.manifest["pictures"][v])).convert("RGB") for k, v in ids.items()}

    def font(self, role):
        if role not in self._fonts:
            h, face, _ = T.FONTS[role]
            if face == "epicons":
                self._fonts[role] = ImageFont.truetype(LUCIDE, int(round(h * 0.8)))
            else:
                self._fonts[role] = ImageFont.truetype(os.path.join(FONTDIR, face + ".ttf"), int(round(h / 1.21)))
        return self._fonts[role]

    def crop(self, layer, x, y, w, h):
        if w > 0 and h > 0:
            self.img.paste(self._layers[layer].crop((x, y, x + w, y + h)), (x, y))

    def fill(self, x, y, w, h, color):
        if w > 0 and h > 0:
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=color)

    def line(self, x0, y0, x1, y1, color):
        self.d.line([(x0, y0), (x1, y1)], fill=color)

    def text(self, x, y, w, h, s, font, color, align=0, valign=1, on="glass"):
        if isinstance(on, (tuple, list)):
            self.fill(x, y, w, h, on)
        else:
            self.crop(on, x, y, w, h)     # like xstr sta=0: the whole box comes from that picture, then the text
        f = self.font(font)
        s = str(s)
        # like xstr: the text is clipped to its box
        box = Image.new("RGBA", (max(1, w), max(1, h)), (0, 0, 0, 0))
        bd = ImageDraw.Draw(box)
        l, t, r, b = bd.textbbox((0, 0), s, font=f, anchor="ls")
        asc, desc = f.getmetrics()
        tw = r - l
        tx = {0: 0, 1: (w - tw) / 2, 2: w - tw}[align] - l
        ty = {0: asc, 1: (h + asc - desc) / 2, 2: h - desc}[valign]
        bd.text((tx, ty), s, font=f, fill=color, anchor="ls")
        self.img.paste(box, (x, y), box)

    def save(self, path, scale=1):
        im = self.img if scale == 1 else self.img.resize((T.W * scale, T.H * scale), Image.NEAREST)
        im.save(path)
