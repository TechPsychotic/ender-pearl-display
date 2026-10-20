"""Screen designer model: a screen = the wallpaper + a list of elements, drawn with the same canvas code the Pi uses
(pi/display/glass/canvas.py), so the TJC instructions it produces are exactly what the display app would send.

Everything an element can use is already in the flashed firmware (pi/display/glass/manifest.json): the wallpapers
(each as bg / glass / focus pictures), the 7 fonts, the 61 icons (font characters), the boot pictures. Nothing here
needs a new firmware. Designs are saved as JSON ({"wallpaper", "elements": [...]})."""
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "pi", "display"))
from glass import canvas as GC  # noqa: E402
from glass import theme as T  # noqa: E402

GLASS = os.path.join(REPO, "pi", "display", "glass")
MANIFEST = json.load(open(os.path.join(GLASS, "manifest.json")))
METRICS = {k: v["widths"] for k, v in json.load(open(os.path.join(GLASS, "metrics.json"))).items()}
ICON_NAMES = list(json.load(open(os.path.join(GLASS, "icons.json")))["codepoints"])
W, H = T.W, T.H

FONT_ROLES = ["small", "label", "body", "value", "big"]           # text fonts (the icon fonts are used by icons)
FONT_TITLES = {"small": "Small 14 px", "label": "Label 18 px", "body": "Body 20 px (medium)", "value": "Value 40 px (semibold)",
               "big": "Big 64 px (digits, % . : - + only)"}
ALIGN = ["left", "center", "right"]
VALIGN = ["top", "middle", "bottom"]
UNDER = ["auto", "glass", "focus", "bg", "solid"]               # what's behind text / icons
UNDER_TITLES = {"auto": "Automatic (the panel under it, else the wallpaper)", "glass": "Glass panel", "focus": "Focused panel",
                "bg": "Wallpaper", "solid": "A solid colour"}
COLORS = {"Text": T.TEXT, "Dim": T.DIM, "Faint": T.FAINT, "Teal": T.TEAL, "Teal text": T.TEAL_TEXT, "Warn": T.WARN,
          "Bad": T.BAD, "Good": T.GOOD, "Black": (0, 0, 0), "White": (255, 255, 255)}

KINDS = {   # type -> (title, default element)
    "panel": ("Glass panel", {"x": 10, "y": 40, "w": 220, "h": 90, "style": "glass", "radius": T.RADIUS, "edge": True}),
    "text": ("Text", {"x": 20, "y": 50, "w": 200, "h": 30, "text": "Hello", "font": "body", "color": T.TEXT, "align": "left",
                      "valign": "middle", "under": "auto", "solid": (0, 0, 0)}),
    "icon": ("Icon", {"x": 20, "y": 50, "w": 30, "h": 30, "icon": "print", "size": "icon", "color": T.TEAL_TEXT, "under": "auto",
                      "solid": (0, 0, 0)}),
    "bar": ("Progress bar", {"x": 20, "y": 110, "w": 200, "h": 5, "value": 40, "color": T.TEAL}),
    "rect": ("Filled box", {"x": 20, "y": 140, "w": 60, "h": 40, "color": T.TEAL}),
    "line": ("Line", {"x": 20, "y": 200, "w": 200, "h": 0, "color": T.EDGE}),
    "circle": ("Circle", {"x": 100, "y": 220, "w": 40, "h": 40, "color": T.TEAL, "filled": True}),
    "picture": ("Picture", {"x": 60, "y": 100, "w": 120, "h": 120, "picture": "boot_morph_7.png"}),
}


def new(kind, **kw):
    e = {"type": kind, **json.loads(json.dumps(KINDS[kind][1])), **kw}
    return e


def tw(s, font):
    """Pixel width of s in a firmware font (exact glyph advances; the display wraps text wider than its box)."""
    w = METRICS.get(font) or {}
    avg = (sum(w.values()) / len(w)) if w else 8
    return sum(w.get(ch, avg) for ch in str(s))


def missing_chars(s, font):
    have = METRICS.get(font) or {}
    return sorted({ch for ch in str(s) if ch not in have})


def warnings(e):
    """Things the display would do differently than the user expects."""
    out = []
    if e["type"] == "text":
        f = e["font"]
        if tw(e["text"], f) > e["w"]:
            out.append(f"Too wide: {tw(e['text'], f):.0f} px of text in a {e['w']} px box. The display wraps it onto a new line.")
        if T.FONTS[f][0] > e["h"]:
            out.append(f"The box is lower than the font ({T.FONTS[f][0]} px): the text gets cut.")
        miss = missing_chars(e["text"], f)
        if miss:
            out.append(f"Not in this font: {' '.join(miss)} (the display shows nothing for them).")
    if e["type"] in ("panel", "rect", "bar", "text", "icon", "picture"):
        if e["x"] < 0 or e["y"] < 0 or e["x"] + e["w"] > W or e["y"] + e["h"] > H:
            out.append("Partly off the screen (240 × 320).")
    return out


class Recorder(GC.TjcCanvas):
    """The Pi's TJC canvas, recording instead of sending."""
    def __init__(self, wallpaper):
        walls = MANIFEST["wallpapers"]
        self.pics = walls.get(wallpaper, next(iter(walls.values())))["pics"]
        self.fonts = MANIFEST["fonts"]
        self.record, self.record_v, self.inflight, self.budget, self.errors = [], 0, 0, 0, []

    def _send(self, cmd):
        self.record.append(cmd)


def rgb565(c):
    return T.rgb(*c)


def _under(e, elements, idx):
    """Automatic background for text / icons: the topmost panel below it in the list that contains it, else the wallpaper."""
    if e.get("under", "auto") != "auto":
        return e["under"]
    for p in reversed(elements[:idx]):
        if p["type"] == "panel" and p["x"] <= e["x"] and p["y"] <= e["y"] and e["x"] + e["w"] <= p["x"] + p["w"] and e["y"] + e["h"] <= p["y"] + p["h"]:
            return "focus" if p["style"] == "focus" else "glass"
    return "bg"


def commands(design):
    """The design as TJC instructions (what the display app would send for this screen)."""
    c = Recorder(design.get("wallpaper"))
    c.background()
    els = design.get("elements") or []
    for i, e in enumerate(els):
        k = e["type"]
        x, y, w, h = int(e["x"]), int(e["y"]), int(e["w"]), int(e["h"])
        if k == "panel":
            c.panel(x, y, w, h, focus=e["style"] == "focus", r=int(e["radius"]), edge=bool(e["edge"]))
        elif k in ("text", "icon"):
            under = _under(e, els, i)
            on = tuple(e["solid"]) if under == "solid" else under
            if k == "text":
                c.text(x, y, w, h, e["text"], e["font"], tuple(e["color"]), ALIGN.index(e["align"]), VALIGN.index(e["valign"]), on)
            else:
                c.icon(x, y, w, h, e["icon"], tuple(e["color"]), e["size"], on)
        elif k == "bar":
            c.bar(x, y, w, h, max(0, min(100, e["value"])) / 100, tuple(e["color"]))
        elif k == "rect":
            c.fill(x, y, w, h, tuple(e["color"]))
        elif k == "line":
            c.line(x, y, x + w, y + h, tuple(e["color"]))
        elif k == "circle":
            r = max(1, int(min(w, h) / 2))
            c._send(f"{'cirs' if e['filled'] else 'cir'} {x + r},{y + r},{r},{rgb565(e['color'])}")
        elif k == "picture" and e["picture"] in MANIFEST["pictures"]:
            c.picture(x, y, MANIFEST["pictures"].index(e["picture"]))
    return c.record


def frame(design):
    """In the shape of GET /api/display/frame, for the mirror renderer."""
    return {"pics": MANIFEST["pictures"], "cmds": commands(design), "dimmed": False}


def bbox(e):
    if e["type"] == "line":
        return min(e["x"], e["x"] + e["w"]) - 3, min(e["y"], e["y"] + e["h"]) - 3, abs(e["w"]) + 6, abs(e["h"]) + 6
    return e["x"], e["y"], e["w"], e["h"]


def hit(design, x, y):
    """Index of the topmost element at (x, y) on the screen, or None."""
    els = design.get("elements") or []
    for i in range(len(els) - 1, -1, -1):
        bx, by, bw, bh = bbox(els[i])
        if bx <= x <= bx + bw and by <= y <= by + bh:
            return i
    return None


def python_code(design):
    """The design as calls on the Pi app's canvas (for pi/display/glass/app.py screens)."""
    lines = ["# generated by the Ender Pearl designer: drop into a Screen.draw(self, c)", "c.background()"]
    els = design.get("elements") or []
    for i, e in enumerate(els):
        k = e["type"]
        x, y, w, h = e["x"], e["y"], e["w"], e["h"]
        if k == "panel":
            lines.append(f"c.panel({x}, {y}, {w}, {h}, focus={e['style'] == 'focus'}, r={e['radius']}, edge={bool(e['edge'])})")
        elif k == "text":
            u = _under(e, els, i)
            on = repr(tuple(e["solid"])) if u == "solid" else repr(u)
            lines.append(f"c.text({x}, {y}, {w}, {h}, {e['text']!r}, {e['font']!r}, {tuple(e['color'])}, {ALIGN.index(e['align'])}, {VALIGN.index(e['valign'])}, {on})")
        elif k == "icon":
            u = _under(e, els, i)
            on = repr(tuple(e["solid"])) if u == "solid" else repr(u)
            lines.append(f"c.icon({x}, {y}, {w}, {h}, {e['icon']!r}, {tuple(e['color'])}, {e['size']!r}, {on})")
        elif k == "bar":
            lines.append(f"c.bar({x}, {y}, {w}, {h}, {e['value'] / 100:.2f}, {tuple(e['color'])})")
        elif k == "rect":
            lines.append(f"c.fill({x}, {y}, {w}, {h}, {tuple(e['color'])})")
        elif k == "line":
            lines.append(f"c.line({x}, {y}, {x + w}, {y + h}, {tuple(e['color'])})")
        elif k == "circle":
            r = max(1, int(min(w, h) / 2))
            lines.append(f"c._send('{'cirs' if e['filled'] else 'cir'} {x + r},{y + r},{r},{rgb565(e['color'])}')")
        elif k == "picture":
            lines.append(f"c.picture({x}, {y}, MANIFEST['pictures'].index({e['picture']!r}))")
    return "\n".join(lines) + "\n"


class LocalAssets:
    """The display's pictures and fonts from this repo (design/assets, the Inter fonts, the icon font), so the designer
    works without the Pi; anything missing comes from the Pi (pi.Pi.asset) when connected."""
    INTER = ("/usr/share/fonts/rsms-inter-fonts", "/usr/share/fonts/inter", "/usr/local/share/fonts")

    def __init__(self, pi=None):
        self.pi = pi

    def asset(self, name):
        if name.startswith("fonts/"):
            f = name[6:]
            cands = [os.path.join(REPO, "design", "icons", f)] + [os.path.join(d, f) for d in self.INTER]
        else:
            cands = [os.path.join(REPO, "design", "assets", name)]
        for c in cands:
            if os.path.exists(c):
                return c
        if self.pi and self.pi.token:
            return self.pi.asset(name)
        raise FileNotFoundError(name)


def picture_size(name):
    from PIL import Image
    p = os.path.join(REPO, "design", "assets", name)
    try:
        return Image.open(p).size
    except OSError:
        return 120, 120


# ---------------------------------------------------------------- templates: starting points that show what's possible
def templates():
    wall = next(iter(MANIFEST["wallpapers"]))
    t = {}
    t["Blank"] = {"wallpaper": wall, "elements": []}
    t["Header and card"] = {"wallpaper": wall, "elements": [
        new("panel", x=0, y=0, w=240, h=30, radius=0, edge=False),
        new("text", x=8, y=2, w=180, h=26, text="My screen", font="body"),
        new("text", x=186, y=2, w=48, h=26, text="12:00", font="label", color=T.DIM, align="right"),
        new("line", x=0, y=30, w=239, h=0, color=(60, 120, 115)),
        new("panel", x=10, y=40, w=220, h=96),
        new("icon", x=20, y=48, w=26, h=24, icon="nozzle", size="icon_s"),
        new("text", x=50, y=48, w=170, h=24, text="Nozzle", font="label", color=T.DIM),
        new("text", x=20, y=74, w=200, h=40, text="215°", font="value"),
        new("bar", x=22, y=122, w=196, h=4, value=85, color=T.WARN)]}
    t["Big number"] = {"wallpaper": wall, "elements": [
        new("panel", x=10, y=60, w=220, h=150, style="focus"),
        new("icon", x=10, y=70, w=220, h=30, icon="speed", color=(220, 255, 250)),
        new("text", x=10, y=104, w=220, h=64, text="100", font="big", align="center"),
        new("text", x=10, y=168, w=220, h=26, text="% speed", font="label", color=T.TEAL_TEXT, align="center"),
        new("bar", x=30, y=196, w=180, h=4, value=50)]}
    t["Tiles"] = {"wallpaper": wall, "elements": []}
    for i, (ic, lab) in enumerate((("print", "Print"), ("prepare", "Prepare"), ("control", "Control"), ("level", "Level"))):
        x, y = 10 + (i % 2) * 114, 60 + (i // 2) * 120
        focus = i == 0
        t["Tiles"]["elements"] += [new("panel", x=x, y=y, w=106, h=110, style="focus" if focus else "glass"),
                                   new("icon", x=x, y=y + 16, w=106, h=40, icon=ic, color=(220, 255, 250) if focus else T.TEAL_TEXT),
                                   new("text", x=x, y=y + 70, w=106, h=26, text=lab, font="body" if focus else "label",
                                       color=T.TEXT if focus else T.DIM, align="center")]
    boot_bg = (8, 12, 15)   # the boot pictures' own background
    t["Splash"] = {"wallpaper": wall, "elements": [
        new("rect", x=0, y=0, w=240, h=320, color=boot_bg),
        new("picture", x=60, y=92, w=120, h=120, picture="boot_morph_7.png"),
        new("text", x=20, y=226, w=200, h=30, text="Ender Pearl", font="body", align="center", under="solid", solid=boot_bg)]}
    return t


def capabilities():
    """What the firmware holds, for the 'What can the display do?' sheet."""
    walls = MANIFEST["wallpapers"]
    return {
        "Screen": "240 × 320 pixels, portrait, 65,536 colours (RGB565). Everything is drawn in order: later elements cover earlier ones.",
        "Wallpapers": f"{len(walls)} built in: {', '.join(n.replace('-', ' ').title() for n in walls)}. Each exists three times: "
                      "the image, a glass version (blurred, dark) and a focused version (lighter). Panels are cut out of those, "
                      "which is how the frosted-glass look works without real transparency.",
        "Fonts": "Inter in five sizes: " + ", ".join(FONT_TITLES[f] for f in FONT_ROLES) +
                 ". Characters: plain English letters, digits, punctuation and ° · ‹ › … – ×. Big only has digits and % . : - +.",
        "Icons": f"{len(ICON_NAMES)} icons in two sizes (24 and 18 px), any colour: " + ", ".join(ICON_NAMES) + ".",
        "Pictures": f"{len(MANIFEST['pictures'])} pictures: the wallpaper layers and the boot animation frames (logo, rotating mark, name).",
        "Shapes": "Filled boxes, lines (1 px), circles (filled or outline), progress bars. No rotation, gradients, "
                  "or transparency beyond the baked glass layers.",
        "Text": "Anti-aliased, clipped to its box, aligned left / centre / right and top / middle / bottom. Text wider than its "
                "box wraps onto the next line, so the designer warns you. Text blends with what's behind it: the glass panel, "
                "the wallpaper, or a solid colour.",
        "Needs a new firmware": "New wallpapers, pictures, fonts or icons: they're stored in the display's flash "
                                "(docs/06-design-and-assets.md). Layouts, colours, texts and positions never do.",
    }
