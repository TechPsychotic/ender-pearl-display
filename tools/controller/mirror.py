"""The printer screen, rebuilt from the display app's recorded drawing commands (GET /api/display/frame) with the
display's own pictures and fonts: the same instructions the TJC display executed, executed again with Pillow."""
from PIL import Image, ImageDraw, ImageFont

W, H = 240, 320
# TJC font ids -> (font file served by /api/display/asset, pixel size) as in the firmware (theme.FONT_ORDER)
FONTS = [("Inter-Regular", 14 / 1.21), ("Inter-Regular", 18 / 1.21), ("Inter-Medium", 20 / 1.21), ("Inter-SemiBold", 40 / 1.21),
         ("Inter-SemiBold", 64 / 1.21), ("epicons", 24 * 0.8), ("epicons", 18 * 0.8)]


def rgb565(v):
    v = int(v)
    return (((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)


class Mirror:
    def __init__(self, pi):
        self.pi = pi
        self.pics = {}
        self.fonts = {}

    def _pic(self, name):
        if name not in self.pics:
            self.pics[name] = Image.open(self.pi.asset(name)).convert("RGB")
        return self.pics[name]

    def _font(self, fid):
        face, px = FONTS[fid] if 0 <= fid < len(FONTS) else FONTS[1]
        key = (face, round(px))
        if key not in self.fonts:
            self.fonts[key] = ImageFont.truetype(self.pi.asset(f"fonts/{face}.ttf"), max(6, round(px)))
        return self.fonts[key], px

    def render(self, frame):
        """frame: {"pics": [file names by picture id], "cmds": [...], "dimmed": bool} -> a 240 x 320 RGB image."""
        img = Image.new("RGB", (W, H), (0, 0, 0))
        d = ImageDraw.Draw(img)
        pics = frame.get("pics") or []
        pic = lambda i: self._pic(pics[i]) if 0 <= i < len(pics) else None
        for c in frame.get("cmds") or []:
            op, _, rest = c.partition(" ")
            try:
                if op == "xpic":
                    x, y, w, h, sx, sy, i = map(int, rest.split(","))
                    p = pic(i)
                    if p and w > 0 and h > 0:
                        img.paste(p.crop((sx, sy, sx + w, sy + h)), (x, y))
                elif op == "pic":
                    x, y, i = map(int, rest.split(","))
                    p = pic(i)
                    if p:
                        img.paste(p, (x, y))
                elif op == "fill":
                    x, y, w, h, col = map(int, rest.split(","))
                    if w > 0 and h > 0:
                        d.rectangle((x, y, x + w - 1, y + h - 1), fill=rgb565(col))
                elif op == "cls":
                    d.rectangle((0, 0, W - 1, H - 1), fill=rgb565(rest))
                elif op == "line":
                    x0, y0, x1, y1, col = map(int, rest.split(","))
                    d.line((x0, y0, x1, y1), fill=rgb565(col))
                elif op == "xstr":
                    self._xstr(img, rest, pic)
            except (ValueError, IndexError, OSError):
                continue   # one bad command doesn't stop the frame
        if frame.get("dimmed"):
            img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), 0.8)
        return img

    def _xstr(self, img, rest, pic):
        q = rest.index('"')
        x, y, w, h, fid, fg, bg, xc, yc, sta = map(int, rest[:q].rstrip(",").split(","))
        text = rest[q + 1:-1]
        if w <= 0 or h <= 0:
            return
        if sta == 0 and pic(bg):            # the box comes from picture bg, then the text (what the display does)
            img.paste(pic(bg).crop((x, y, x + w, y + h)), (x, y))
        elif sta == 1:
            ImageDraw.Draw(img).rectangle((x, y, x + w - 1, y + h - 1), fill=rgb565(bg))
        font, px = self._font(fid)
        box = img.crop((x, y, x + w, y + h))
        bd = ImageDraw.Draw(box)
        ax = {0: ("l", 0), 1: ("m", w / 2), 2: ("r", w)}.get(xc, ("l", 0))
        ty = px * 0.6 if yc == 0 else h - px * 0.6 if yc == 2 else h / 2
        bd.text((ax[1], ty), text, font=font, fill=rgb565(fg), anchor=ax[0] + "m")
        img.paste(box, (x, y))              # clipped to its box, like the display
