"""Ender Loop display design: backgrounds, glass layers and screen mockups (240 x 320, portrait).

Everything here is something the TJC display can reproduce at run time:
  * full-screen pictures in the firmware: the background, its "glass" version (blur + dark tint + faint teal) and a
    "focus" version (brighter, more teal);
  * a panel = the same rectangle cropped from the glass picture (xpic), rounded corners by cropping the plain
    background back into the corner pixels, a 1 px top highlight line;
  * text = anti-aliased Inter drawn with xstr, its background cropped from the picture underneath.
    python3 render.py            # writes out/*.png and out/sheet.png (2x, for viewing)"""
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 240, 320
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
FONT = "/usr/share/fonts/rsms-inter-fonts/Inter-{}.ttf"
TEAL = (45, 212, 191)          # teal green accent
TEAL_TEXT = (153, 246, 228)
TXT, DIM = (236, 242, 245), (150, 165, 172)
WARN = (251, 191, 36)


def font(size, weight="Regular"):
    for w in (weight, "Regular"):
        p = FONT.format(w)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------- backgrounds
def grain(img, amount=6, seed=1):
    rnd = random.Random(seed)
    n = Image.new("L", img.size)
    n.putdata([128 + rnd.randint(-amount, amount) for _ in range(img.size[0] * img.size[1])])
    return ImageChops.add(img, Image.merge("RGB", (n, n, n)), 1, -128)


def bg_aurora(seed=3):
    img = Image.new("RGB", (W, H), (6, 10, 14))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    rnd = random.Random(seed)
    for (cx, cy, r, c) in [(30, 50, 110, (8, 62, 58)), (220, 170, 120, (8, 44, 62)), (80, 300, 130, (12, 70, 52)),
                           (210, 10, 60, (30, 20, 58))]:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=c)
    glow = glow.filter(ImageFilter.GaussianBlur(55))
    img = ImageChops.add(img, glow)
    d2 = ImageDraw.Draw(img)
    for _ in range(26):   # a few soft bokeh dots
        x, y, r = rnd.randint(0, W), rnd.randint(0, H), rnd.randint(1, 3)
        d2.ellipse([x - r, y - r, x + r, y + r], fill=(40, 110, 102))
    return grain(img.filter(ImageFilter.GaussianBlur(0.6)), 5, seed)


def bg_layers(seed=5):
    """3D-print layer lines: contour bands of a smooth surface, glowing teal on near black."""
    img = Image.new("RGB", (W, H), (5, 9, 12))
    d = ImageDraw.Draw(img)
    f = lambda x, y: (math.sin(x / 41 + 0.8) * 30 + math.cos(y / 53) * 34 + math.sin((x + y) / 29) * 14 + y * 0.35)
    for level in range(-60, 200, 7):
        pts = []
        for x in range(0, W + 1, 2):
            # find y where f(x, y) == level by scanning (coarse but fine for art)
            for y in range(0, H, 1):
                if f(x, y) >= level:
                    pts.append((x, y)); break
        if len(pts) > 2:
            a = max(18, 120 - abs(level - 70))
            d.line(pts, fill=(20, int(a * 0.9), int(a * 0.85)), width=1)
    glow = img.filter(ImageFilter.GaussianBlur(6))
    img = ImageChops.add(img, glow)
    vign = Image.new("L", (W, H), 0)
    ImageDraw.Draw(vign).ellipse([-80, -40, W + 80, H + 60], fill=255)
    img = Image.composite(img, Image.new("RGB", (W, H), (2, 4, 6)), vign.filter(ImageFilter.GaussianBlur(40)))
    return grain(img, 4, seed)


def bg_grid(seed=7):
    """A print bed in perspective, grid lines glowing teal, fading into the dark."""
    img = Image.new("RGB", (W, H), (5, 8, 12))
    d = ImageDraw.Draw(img)
    hy, vx = 120, W / 2
    for i in range(-12, 13):
        x_bottom = vx + i * 34
        d.line([(vx + i * 3, hy), (x_bottom, H + 40)], fill=(12, 58, 56), width=1)
    y, k = hy, 2.0
    while y < H:
        d.line([(0, y), (W, y)], fill=(12, int(40 + (y - hy) * 0.12), int(38 + (y - hy) * 0.11)), width=1)
        k *= 1.18; y += k
    glow = Image.new("RGB", (W, H))
    ImageDraw.Draw(glow).ellipse([-40, 70, W + 40, 220], fill=(12, 58, 56))
    img = ImageChops.add(img, glow.filter(ImageFilter.GaussianBlur(45)))
    img = ImageChops.add(img, img.filter(ImageFilter.GaussianBlur(4)))
    return grain(img, 4, seed)


BACKGROUNDS = {"aurora": bg_aurora, "layers": bg_layers, "grid": bg_grid}


def glass_of(bg, focus=False):
    """What any panel looks like: the background blurred, darkened, faintly teal (more teal and lighter when focused)."""
    g = bg.filter(ImageFilter.GaussianBlur(14))
    tint = Image.new("RGB", (W, H), (20, 52, 56) if focus else (12, 20, 24))
    g = Image.blend(g, tint, 0.45 if focus else 0.55)
    light = Image.new("RGB", (W, H), (255, 255, 255))
    g = Image.blend(g, light, 0.06 if focus else 0.03)
    if focus:
        g = Image.blend(g, Image.new("RGB", (W, H), TEAL), 0.10)
    return g


# ---------------------------------------------------------------- drawing like the display
class Screen:
    def __init__(self, bg):
        self.bg, self.glass, self.focus = bg, glass_of(bg), glass_of(bg, True)
        self.img = bg.copy()
        self.d = ImageDraw.Draw(self.img)

    def panel(self, x, y, w, h, r=10, focus=False, border=True):
        src = self.focus if focus else self.glass
        self.img.paste(src.crop((x, y, x + w, y + h)), (x, y))
        for yy in range(r):   # rounded corners: put the plain background back outside the arc (hard edge, as on the display)
            dx = r - int(math.sqrt(max(0, r * r - (r - yy - 0.5) ** 2)))
            for (px, py) in ((x, y + yy), (x + w - dx, y + yy), (x, y + h - 1 - yy), (x + w - dx, y + h - 1 - yy)):
                if dx > 0:
                    self.img.paste(self.bg.crop((px, py, px + dx, py + 1)), (px, py))
        if border:
            hl = (120, 230, 215) if focus else (70, 90, 98)
            self.d.line([(x + r, y), (x + w - r, y)], fill=hl)                      # top highlight
            if focus:
                self.d.line([(x + r, y + h - 1), (x + w - r, y + h - 1)], fill=(60, 160, 150))
        return self

    def text(self, x, y, s, size=16, color=TXT, weight="Regular", anchor="la"):
        self.d.text((x, y), s, font=font(size, weight), fill=color, anchor=anchor)

    def bar(self, x, y, w, h, frac, color=TEAL):
        self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=(30, 44, 48))
        if frac > 0:
            self.d.rectangle([x, y, x + int((w - 1) * frac), y + h - 1], fill=color)


# ---------------------------------------------------------------- icons (line art, drawn like they'd be baked in)
def icon(d, kind, cx, cy, s=22, c=TEAL_TEXT, wdt=2):
    h = s / 2
    if kind == "print":      # play triangle in a cube-ish frame
        d.polygon([(cx - h * 0.45, cy - h * 0.6), (cx - h * 0.45, cy + h * 0.6), (cx + h * 0.65, cy)], outline=c, width=wdt)
    elif kind == "prepare":  # sliders
        for i, k in enumerate((-0.6, 0, 0.6)):
            y = cy + k * h
            d.line([(cx - h, y), (cx + h, y)], fill=c, width=wdt)
            px = cx + (0.4, -0.5, 0.2)[i] * h
            d.ellipse([px - 3, y - 3, px + 3, y + 3], fill=c)
    elif kind == "tune":     # gauge
        d.arc([cx - h, cy - h, cx + h, cy + h], 180, 360, fill=c, width=wdt)
        d.line([(cx, cy), (cx + h * 0.6, cy - h * 0.55)], fill=c, width=wdt)
    elif kind == "info":
        d.ellipse([cx - h, cy - h, cx + h, cy + h], outline=c, width=wdt)
        d.line([(cx, cy - 1), (cx, cy + h * 0.5)], fill=c, width=wdt)
        d.ellipse([cx - 1.5, cy - h * 0.5 - 1.5, cx + 1.5, cy - h * 0.5 + 1.5], fill=c)
    elif kind == "nozzle":
        d.polygon([(cx - h * 0.7, cy - h), (cx + h * 0.7, cy - h), (cx + h * 0.7, cy - h * 0.1), (cx + h * 0.25, cy + h * 0.5),
                   (cx - h * 0.25, cy + h * 0.5), (cx - h * 0.7, cy - h * 0.1)], outline=c, width=wdt)
        d.line([(cx, cy + h * 0.7), (cx, cy + h)], fill=c, width=wdt)
    elif kind == "bed":
        d.rectangle([cx - h, cy + h * 0.2, cx + h, cy + h * 0.5], outline=c, width=wdt)
        for k in (-0.5, 0, 0.5):
            x = cx + k * h
            d.arc([x - 3, cy - h * 0.8, x + 3, cy - h * 0.2], 90, 270, fill=c, width=1)
            d.arc([x - 3, cy - h * 0.4, x + 3, cy + h * 0.1], 270, 90, fill=c, width=1)
    elif kind == "pause":
        for k in (-0.35, 0.35):
            d.rectangle([cx + k * h - 2.5, cy - h * 0.6, cx + k * h + 2.5, cy + h * 0.6], fill=c)
    elif kind == "stop":
        d.rectangle([cx - h * 0.55, cy - h * 0.55, cx + h * 0.55, cy + h * 0.55], outline=c, width=wdt)
    elif kind == "home":
        d.line([(cx - h, cy), (cx, cy - h), (cx + h, cy)], fill=c, width=wdt)
        d.rectangle([cx - h * 0.65, cy, cx + h * 0.65, cy + h * 0.8], outline=c, width=wdt)
    elif kind == "move":
        for a in (0, 90, 180, 270):
            r = math.radians(a)
            d.line([(cx, cy), (cx + math.cos(r) * h, cy + math.sin(r) * h)], fill=c, width=wdt)
    elif kind == "heat":
        d.line([(cx, cy - h), (cx, cy + h * 0.3)], fill=c, width=wdt + 1)
        d.ellipse([cx - 5, cy + h * 0.2, cx + 5, cy + h * 0.2 + 10], outline=c, width=wdt)
    elif kind == "cool":
        for a in (0, 60, 120):
            r = math.radians(a)
            d.line([(cx - math.cos(r) * h, cy - math.sin(r) * h), (cx + math.cos(r) * h, cy + math.sin(r) * h)], fill=c, width=wdt)
    elif kind == "chev":
        d.line([(cx - 3, cy - 6), (cx + 3, cy), (cx - 3, cy + 6)], fill=c, width=wdt)


# ---------------------------------------------------------------- screens
def header(s, title="Ender Loop"):
    s.panel(0, 0, W, 30, r=0, border=False)
    s.d.line([(0, 30), (W, 30)], fill=(60, 120, 115))
    s.text(12, 7, title, 15, TXT, "SemiBold")
    s.text(W - 12, 7, "21:42", 15, DIM, anchor="ra")


def temp_card(s, x, y, w, kind, label, now, target, frac):
    s.panel(x, y, w, 92)
    icon(s.d, kind, x + 20, y + 22, 20)
    s.text(x + 38, y + 14, label, 13, DIM)
    s.text(x + 14, y + 34, f"{now:.0f}", 32, TXT, "SemiBold")
    s.text(x + 14 + font(32, "SemiBold").getlength(f"{now:.0f}") + 2, y + 38, "°C", 13, DIM)
    s.text(x + 14, y + 66, f"target {target:.0f}°", 11, DIM)
    s.bar(x + 14, y + 83, w - 28, 3, frac, TEAL if frac >= 0.98 or target == 0 else WARN)


def tile(s, x, y, w, h, kind, label, focus=False):
    s.panel(x, y, w, h, focus=focus)
    icon(s.d, kind, x + w // 2, y + h // 2 - 9, 24, TEAL_TEXT if not focus else (220, 255, 250))
    s.text(x + w // 2, y + h - 22, label, 13, TXT if focus else DIM, "Medium", anchor="ma")


def home_idle(bg):
    s = Screen(bg)
    header(s)
    temp_card(s, 10, 40, 106, "nozzle", "Nozzle", 196, 200, 0.97)
    temp_card(s, 124, 40, 106, "bed", "Bed", 55, 55, 1.0)
    s.panel(10, 140, 220, 34)
    s.text(22, 149, "Idle  ·  PLA loaded", 14, TXT)
    s.text(218, 149, "●", 14, TEAL, anchor="ra")
    tile(s, 10, 184, 106, 62, "print", "Print", focus=True)
    tile(s, 124, 184, 106, 62, "prepare", "Prepare")
    tile(s, 10, 252, 106, 62, "tune", "Control")
    tile(s, 124, 252, 106, 62, "info", "Info")
    return s.img


def home_printing(bg):
    s = Screen(bg)
    header(s, "Printing")
    s.panel(10, 40, 220, 128)
    s.text(22, 50, "benchy_pla_0.2mm.gcode", 13, DIM)
    s.text(22, 68, "47", 52, TXT, "SemiBold")
    s.text(22 + font(52, "SemiBold").getlength("47") + 4, 92, "%", 20, TEAL_TEXT, "Medium")
    s.text(218, 76, "1h 12m left", 14, TXT, anchor="ra")
    s.text(218, 96, "done 22:54", 13, DIM, anchor="ra")
    s.bar(22, 132, 196, 6, 0.47)
    s.text(22, 146, "Layer 94 / 200", 13, DIM)
    s.text(218, 146, "z 18.80", 13, DIM, anchor="ra")
    s.panel(10, 176, 106, 40)
    icon(s.d, "nozzle", 28, 196, 16)
    s.text(42, 187, "200°", 16, TXT, "Medium")
    s.panel(124, 176, 106, 40)
    icon(s.d, "bed", 142, 196, 16)
    s.text(156, 187, "55°", 16, TXT, "Medium")
    tile(s, 10, 224, 69, 90, "pause", "Pause", focus=True)
    tile(s, 85, 224, 70, 90, "tune", "Tune")
    tile(s, 161, 224, 69, 90, "stop", "Stop")
    return s.img


def menu(bg):
    s = Screen(bg)
    header(s, "Prepare")
    rows = [("home", "Home all axes"), ("move", "Move axes"), ("heat", "Preheat PLA"), ("heat", "Preheat PETG"),
            ("cool", "Cool down"), ("nozzle", "Nozzle temperature"), ("bed", "Bed temperature")]
    for i, (k, label) in enumerate(rows):
        y = 40 + i * 39
        s.panel(10, y, 220, 34, r=8, focus=(i == 2))
        icon(s.d, k, 30, y + 17, 16, TEAL_TEXT if i != 2 else (220, 255, 250))
        s.text(48, y + 9, label, 14, TXT if i == 2 else (205, 214, 218), "Medium" if i == 2 else "Regular")
        icon(s.d, "chev", 214, y + 17, 12, DIM)
    return s.img


def main():
    os.makedirs(OUT, exist_ok=True)
    bgs = {k: f() for k, f in BACKGROUNDS.items()}
    tiles = []
    for k, bg in bgs.items():
        bg.save(os.path.join(OUT, f"bg_{k}.png"))
        glass_of(bg).save(os.path.join(OUT, f"bg_{k}_glass.png"))
        glass_of(bg, True).save(os.path.join(OUT, f"bg_{k}_focus.png"))
        for name, fn in (("home", home_idle), ("printing", home_printing), ("menu", menu)):
            im = fn(bg)
            im.save(os.path.join(OUT, f"{k}_{name}.png"))
            tiles.append(im)
    # contact sheet: rows = backgrounds, columns = screens, 2x, with gaps
    gap, sc = 16, 2
    sheet = Image.new("RGB", (3 * W * sc + 4 * gap, 3 * H * sc + 4 * gap), (24, 26, 30))
    for i, im in enumerate(tiles):
        r, c = divmod(i, 3)
        sheet.paste(im.resize((W * sc, H * sc), Image.NEAREST), (gap + c * (W * sc + gap), gap + r * (H * sc + gap)))
    sheet.save(os.path.join(OUT, "sheet.png"))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
