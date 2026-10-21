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
    "bar": ("Progress bar", {"x": 20, "y": 110, "w": 200, "h": 5, "value": 40, "source": "fixed", "color": T.TEAL,
                             "track": T.TRACK, "radius": 0}),
    "rect": ("Filled box", {"x": 20, "y": 140, "w": 60, "h": 40, "color": T.TEAL, "radius": 0}),
    "line": ("Line", {"x": 20, "y": 200, "w": 200, "h": 0, "color": T.EDGE}),
    "circle": ("Circle", {"x": 100, "y": 220, "w": 40, "h": 40, "color": T.TEAL, "filled": True}),
    "picture": ("Picture", {"x": 60, "y": 100, "w": 120, "h": 120, "picture": "boot_morph_7.png", "radius": 0}),
    "preview": ("3D print preview", {"x": 14, "y": 142, "w": 98, "h": 70, "file": "", "view": "layers", "layer": -1,
                                     "done": T.PREVIEW_DONE, "todo": T.PREVIEW_TODO, "shade": False}),
    "ctext": ("Custom font text", {"x": 20, "y": 60, "w": 200, "h": 50, "text": "Custom", "font_file": "", "size": 36,
                                   "color": T.TEXT, "align": "center", "smooth": 3, "under": "auto", "solid": (0, 0, 0)}),
    "cimage": ("Custom image", {"x": 70, "y": 110, "w": 100, "h": 100, "image_file": "", "colors": 16, "radius": 0}),
}
ROUNDED = {"panel", "rect", "bar", "picture", "cimage"}          # elements with a corner radius
VIEWS = {"plate": "Whole plate, 3D (file details)", "layers": "Printed so far, 3D (live preview)", "objects": "Objects, top view (skip object)"}
SRC_SIZE = {"plate": (204, 88), "layers": (98, 70), "objects": (204, 150)}   # sizes the Pi pre-builds (server/display_api.py SIZES)
BAR_SOURCES = {"fixed": "Fixed value", "progress": "Print progress", "nozzle": "Nozzle heating (now / target)",
               "bed": "Bed heating (now / target)", "layer": "Layer (current / total)"}
DATA_FIELDS = {"nozzle": "Nozzle °C", "nozzle_target": "Nozzle target °C", "bed": "Bed °C", "bed_target": "Bed target °C",
               "progress": "Progress %", "time_left": "Time left", "done_at": "Finishes at", "elapsed": "Printing for",
               "layer": "Layer", "layers": "Layers in total", "z": "Height (mm)", "file": "File name", "state": "State",
               "filament": "Filament loaded", "speed": "Speed %", "flow": "Flow %", "clock": "Clock (HH:MM)"}
SAMPLE_DATA = {"nozzle": "215", "nozzle_target": "215", "bed": "70", "bed_target": "70", "progress": "42", "time_left": "1h 12m",
               "done_at": "14:35", "elapsed": "48m", "layer": "84", "layers": "200", "z": "16.8", "file": "benchy_petg.gcode",
               "state": "Printing", "filament": "PETG", "speed": "100", "flow": "100", "clock": "12:00",
               "_frac": {"progress": 0.42, "nozzle": 1.0, "bed": 1.0, "layer": 0.42}, "_layer": 83, "_job": None}


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


def warnings(e, design=None, ctx=None):
    """Things the display would do differently than the user expects."""
    import re as _re
    out = []
    if e["type"] in ("text", "ctext"):
        bad = [f for f in _re.findall(r"\{(\w+)\}", str(e["text"])) if f not in DATA_FIELDS]
        if bad:
            out.append(f"Unknown live data: {', '.join('{' + b + '}' for b in bad)} (see “Insert live data”).")
    if e["type"] == "ctext" and e["font_file"] and not os.path.exists(e["font_file"]):
        out.append("The font file isn't on this computer any more.")
    if e["type"] == "cimage" and not (e["image_file"] and os.path.exists(e["image_file"])):
        out.append("Choose an image file (PNG, JPG…).")
    if e["type"] == "preview":
        sw, sh = SRC_SIZE[e["view"]]
        if e["w"] < sw * 0.6 or e["h"] < sh * 0.6:
            out.append(f"Small box: the preview is drawn at {min(e['w'] / sw, e['h'] / sh):.0%} of its size (it is built for {sw} × {sh}).")
    if design is not None and e["type"] in ("ctext", "cimage", "preview"):
        idx = design["elements"].index(e)
        cmds = element_commands(design, idx, ctx)
        ms = estimate_ms(cmds)
        if ms > 1500:
            out.append(f"Slow to draw: {len(cmds)} commands, about {ms / 1000:.1f} s on the display. Fine for a still "
                       "screen, too slow for values that change often.")
    if e["type"] == "text":
        f = e["font"]
        shown = fill_text(e["text"], (ctx or {}).get("data"))
        if tw(shown, f) > e["w"]:
            out.append(f"Too wide: {tw(shown, f):.0f} px of text in a {e['w']} px box. The display wraps it onto a new line.")
        if T.FONTS[f][0] > e["h"]:
            out.append(f"The box is lower than the font ({T.FONTS[f][0]} px): the text gets cut.")
        miss = missing_chars(shown, f)
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


def rounded_blocks(x, y, w, h, r):
    """A rounded rectangle as row blocks (x, y, w, h): what is outside the corners isn't drawn, so whatever is
    underneath shows through (the same corner curve as canvas.panel)."""
    r = max(0, min(int(r), w // 2, h // 2))
    if r <= 0:
        return [(x, y, w, h)]
    top, bottom = [], []
    for yy in range(r):
        dx = r - int(math.sqrt(max(0.0, r * r - (r - yy - 0.5) ** 2)))
        top.append((x + dx, y + yy, w - 2 * dx, 1))
        bottom.append((x + dx, y + h - 1 - yy, w - 2 * dx, 1))
    return top + ([(x, y + r, w, h - 2 * r)] if h - 2 * r > 0 else []) + bottom[::-1]


def fmt_dur(sec):
    if sec is None:
        return "–"
    m = int(sec // 60)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def data_from_state(st):
    """The live data fields from the printer's /api/state (progress by time, like the display app)."""
    import time as _t
    st = st or {}
    s = st.get("status") or {}
    printing = bool(st.get("printing"))
    t = (s.get("temps") if printing else st.get("idle_temps")) or [0, 0, 0, 0]
    left = s.get("remaining")
    if left is not None:
        left = max(0, left - (_t.time() - s.get("updated", _t.time())))
    el = _t.time() - s["started"] if printing and s.get("started") else 0
    pct = 100.0 * el / (el + left) if left is not None and el > 0 else (100.0 * s.get("sent", 0) / s["total"] if s.get("total") else 0)
    pct = 100.0 if s.get("state") == "done" else min(pct, 99.0) if printing else 0
    ov = s.get("overrides") or {}
    fam = (st.get("filament") or {}).get("family")
    frac = lambda a, b: max(0.0, min(1.0, a / b)) if b else 0.0
    return {"nozzle": f"{t[0]:.0f}", "nozzle_target": f"{t[1]:.0f}", "bed": f"{t[2]:.0f}", "bed_target": f"{t[3]:.0f}",
            "progress": f"{int(pct)}" if printing else "–", "time_left": fmt_dur(left) if printing else "–",
            "done_at": _t.strftime("%H:%M", _t.localtime(s["finish_at"])) if printing and s.get("finish_at") else "–",
            "elapsed": fmt_dur(el) if printing else "–", "layer": str(s.get("layer", -1) + 1) if printing else "–",
            "layers": str(s.get("layers") or "–") if printing else "–", "z": f"{s.get('z') or 0:.1f}" if printing else "–",
            "file": st.get("job") or "–" if printing else "–",
            "state": ("Paused" if s.get("state") == "paused" else "Printing") if printing else "Idle",
            "filament": fam or "none", "speed": f"{ov.get('speed', 1) * 100:.0f}", "flow": f"{ov.get('flow', 1) * 100:.0f}",
            "clock": _t.strftime("%H:%M"),
            "_frac": {"progress": pct / 100 if printing else 0.0, "nozzle": frac(t[0], t[1]), "bed": frac(t[2], t[3]),
                      "layer": frac(s.get("layer", -1) + 1, s.get("layers") or 0) if printing else 0.0},
            "_layer": s.get("layer", -1) if printing else -1, "_job": st.get("job") if printing else None}


class _Blank(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def fill_text(text, data):
    """{field} placeholders -> live values (unknown ones stay as they are)."""
    try:
        return str(text).format_map(_Blank({k: v for k, v in (data or SAMPLE_DATA).items() if not k.startswith("_")}))
    except (ValueError, IndexError):
        return str(text)


def preview_key(e, data):
    """Which pre-built preview an element needs: (view, file, layer); file "" = the current print."""
    f = e.get("file") or (data or {}).get("_job") or ""
    layer = int(e.get("layer", -1))
    if e["view"] == "layers" and layer < 0:
        layer = (data or {}).get("_layer", -1)
    return (e["view"], f, layer if e["view"] == "layers" else None)


def _shade(level):
    lo, hi = (25, 95, 90), T.TEAL_TEXT
    return tuple(int(lo[k] + (hi[k] - lo[k]) * max(0.0, min(1.0, level))) for k in range(3))


# ---------------------------------------------------------------- custom rendering: any font / image as runs of fills
_RUNS = {}


def _runs_from(img_rgb, mask=None):
    """Rows of equal colour -> (x, y, w, colour) runs; masked-out (transparent) pixels are skipped."""
    w, h = img_rgb.size
    px = img_rgb.load()
    mk = mask.load() if mask is not None else None
    out = []
    for yy in range(h):
        xx = 0
        while xx < w:
            if mk is not None and not mk[xx, yy]:
                xx += 1
                continue
            c = px[xx, yy]
            x0 = xx
            while xx < w and px[xx, yy] == c and (mk is None or mk[xx, yy]):
                xx += 1
            out.append((x0, yy, xx - x0, rgb565(c)))
    return out


def custom_text_runs(e, under_rgb, data=None):
    from PIL import Image, ImageDraw, ImageFont
    text = fill_text(e["text"], data)
    key = ("t", text, e["font_file"], e["size"], tuple(e["color"]), e["align"], e["smooth"], tuple(under_rgb), e["w"], e["h"],
           os.path.getmtime(e["font_file"]) if e["font_file"] and os.path.exists(e["font_file"]) else 0)
    if key in _RUNS:
        return _RUNS[key]
    try:
        font = ImageFont.truetype(e["font_file"], int(e["size"])) if e["font_file"] else ImageFont.load_default(int(e["size"]))
    except OSError:
        font = ImageFont.load_default(int(e["size"]))
    w, h = max(1, int(e["w"])), max(1, int(e["h"]))
    m = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(m)
    ax = {"left": ("l", 0), "center": ("m", w / 2), "right": ("r", w)}[e["align"]]
    d.text((ax[1], h / 2), text, font=font, fill=255, anchor=ax[0] + "m")
    levels = max(1, min(4, int(e["smooth"])))
    fg, bg = tuple(e["color"]), tuple(under_rgb)
    q = m.point(lambda a: 0 if a < 255 / (2 * levels) else min(levels, round(a / 255 * levels)))   # alpha in levels 0..n
    col = Image.new("RGB", (w, h))
    cp, qp = col.load(), q.load()
    for yy in range(h):
        for xx in range(w):
            k = qp[xx, yy]
            if k:
                t = k / levels
                cp[xx, yy] = tuple(round(bg[i] + (fg[i] - bg[i]) * t) for i in range(3))
    runs = _runs_from(col, q.point(lambda a: 255 if a else 0))
    _RUNS[key] = runs
    return runs


def custom_image_runs(e):
    from PIL import Image
    f = e["image_file"]
    if not f or not os.path.exists(f):
        return []
    key = ("i", f, os.path.getmtime(f), e["w"], e["h"], e["colors"])
    if key in _RUNS:
        return _RUNS[key]
    im = Image.open(f).convert("RGBA")
    w, h = max(1, int(e["w"])), max(1, int(e["h"]))
    im.thumbnail((w, h), Image.LANCZOS)                      # fit inside the box, keep proportions
    canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
    alpha = canvas.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
    rgb = canvas.convert("RGB").quantize(colors=max(2, min(64, int(e["colors"]))), method=Image.Quantize.MEDIANCUT,
                                         dither=Image.Dither.NONE).convert("RGB")
    runs = _runs_from(rgb, alpha)
    _RUNS[key] = runs
    return runs


def _under_rgb(e, els, idx, wallpaper):
    """The colour behind custom text, for its smooth edges: the average of the picture there, or the solid colour."""
    from PIL import Image
    u = _under(e, els, idx)
    if isinstance(u, tuple):
        return u
    if u == "solid":
        return tuple(e["solid"])
    pics = MANIFEST["wallpapers"].get(wallpaper, next(iter(MANIFEST["wallpapers"].values())))["pics"]
    try:
        im = Image.open(os.path.join(REPO, "design", "assets", MANIFEST["pictures"][pics[u]])).convert("RGB")
        reg = im.crop((max(0, e["x"]), max(0, e["y"]), min(W, e["x"] + e["w"]), min(H, e["y"] + e["h"]))).resize((1, 1), Image.BOX)
        return reg.getpixel((0, 0))
    except (OSError, IndexError, ValueError):
        return (20, 30, 34)


def estimate_ms(cmds):
    """Roughly how long the display takes for these (measured at 921600 baud: fill 0.25 ms, a full-screen picture 62 ms)."""
    t = 0.0
    for c in cmds:
        op, _, rest = c.partition(" ")
        try:
            n = [int(v) for v in rest.split('"')[0].strip(",").split(",") if v.strip().lstrip("-").isdigit()]
        except ValueError:
            n = []
        if op in ("xpic", "fill") and len(n) >= 4:
            t += 0.25 + n[2] * n[3] * 0.0008
        elif op == "line" and len(n) >= 4:
            t += 0.4 + math.hypot(n[2] - n[0], n[3] - n[1]) * 0.012
        elif op == "xstr":
            t += 1.5
        elif op in ("cir", "cirs") and len(n) >= 3:
            t += 0.5 + n[2] * n[2] * 0.003
        else:
            t += 1.0
    return t


def _under(e, elements, idx):
    """Automatic background for text / icons: the topmost panel below it in the list that contains it, else the wallpaper."""
    if e.get("under", "auto") != "auto":
        return e["under"]
    for p in reversed(elements[:idx]):
        inside = p["x"] <= e["x"] and p["y"] <= e["y"] and e["x"] + e["w"] <= p["x"] + p["w"] and e["y"] + e["h"] <= p["y"] + p["h"]
        if inside and p["type"] == "panel":
            return "focus" if p["style"] == "focus" else "glass"
        if inside and p["type"] == "rect":       # on a filled box: blend with its colour
            return tuple(p["color"])
    return "bg"


def commands(design, ctx=None):
    """The design as TJC instructions (what the display app would send for this screen). ctx: {"data": live fields
    (data_from_state), "paths": {preview_key: paths from the Pi}}; without it, sample data and placeholders."""
    ctx = ctx or {}
    data = ctx.get("data") or SAMPLE_DATA
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
            on = under if isinstance(under, tuple) else tuple(e["solid"]) if under == "solid" else under
            if k == "text":
                c.text(x, y, w, h, fill_text(e["text"], data), e["font"], tuple(e["color"]), ALIGN.index(e["align"]), VALIGN.index(e["valign"]), on)
            else:
                c.icon(x, y, w, h, e["icon"], tuple(e["color"]), e["size"], on)
        elif k == "bar":
            src = e.get("source", "fixed")
            frac = max(0, min(100, e["value"])) / 100 if src == "fixed" else data.get("_frac", {}).get(src, 0.0)
            xd = x + (int(round((w - 1) * frac)) if frac > 0 else 0)
            for bx, by, bw, bh in rounded_blocks(x, y, w, h, e.get("radius", 0)):
                a, b = bx, min(bx + bw, xd)
                if b > a:
                    c.fill(a, by, b - a, bh, tuple(e["color"]))
                a = max(bx, xd)
                if bx + bw > a:
                    c.fill(a, by, bx + bw - a, bh, tuple(e.get("track", T.TRACK)))
        elif k == "rect":
            for b in rounded_blocks(x, y, w, h, e.get("radius", 0)):
                c.fill(*b, tuple(e["color"]))
        elif k == "line":
            c.line(x, y, x + w, y + h, tuple(e["color"]))
        elif k == "circle":
            r = max(1, int(min(w, h) / 2))
            c._send(f"{'cirs' if e['filled'] else 'cir'} {x + r},{y + r},{r},{rgb565(e['color'])}")
        elif k == "picture" and e["picture"] in MANIFEST["pictures"]:
            pid = MANIFEST["pictures"].index(e["picture"])
            if int(e.get("radius", 0)) > 0:   # strips of the picture, leaving the corners
                for bx, by, bw, bh in rounded_blocks(x, y, w, h, e["radius"]):
                    c._send(f"xpic {bx},{by},{bw},{bh},{bx - x},{by - y},{pid}")
            else:
                c.picture(x, y, pid)
        elif k == "preview":
            paths = (ctx.get("paths") or {}).get(preview_key(e, ctx.get("data")))
            if not paths:
                why = "connect to the Pi" if not ctx.get("data") else "no print, pick a file" if not preview_key(e, data)[1] else "loading…"
                c.text(x, y, w, h, f"3D preview: {why}", "small", T.DIM, 1, 1, _under(e, els, i))
                continue
            sw, sh = SRC_SIZE[e["view"]]
            s = min(w / sw, h / sh)
            ox, oy = x + (w - sw * s) / 2, y + (h - sh * s) / 2
            P = lambda p: (int(round(ox + p[0] * s)), int(round(oy + p[1] * s)))
            if e["view"] == "objects":
                polys = [(poly, tuple(e["done"])) for ob in paths for poly in ob["paths"]]
            else:
                polys = []
                for q in sorted(paths, key=lambda q: bool(q[-1]) if len(q) > 2 else 0):   # grey still-to-print first, printed on top
                    done = q[2] if len(q) > 2 else True
                    col = (_shade(q[1]) if e.get("shade") else tuple(e["done"])) if done else tuple(e["todo"])
                    polys.append((q[0], col))
            for poly, col in polys:
                pts = [P(p) for p in poly]
                for a, b in zip(pts, pts[1:]):
                    c.line(a[0], a[1], b[0], b[1], col)
        elif k == "ctext":
            for rx, ry, rw, col in custom_text_runs(e, _under_rgb(e, els, i, design.get("wallpaper")), data):
                c._send(f"fill {x + rx},{y + ry},{rw},1,{col}")
        elif k == "cimage":
            rb = rounded_blocks(0, 0, w, h, e.get("radius", 0))
            for rx, ry, rw, col in custom_image_runs(e):
                if int(e.get("radius", 0)) > 0:   # clip each run to the rounded rectangle's row
                    row = next(((bx, bw) for bx, by, bw, bh in rb if by <= ry < by + bh), None)
                    if not row:
                        continue
                    a, b = max(rx, row[0]), min(rx + rw, row[0] + row[1])
                    if b <= a:
                        continue
                    rx, rw = a, b - a
                c._send(f"fill {x + rx},{y + ry},{rw},1,{col}")
    return c.record


def frame(design, ctx=None):
    """In the shape of GET /api/display/frame, for the mirror renderer."""
    return {"pics": MANIFEST["pictures"], "cmds": commands(design, ctx), "dimmed": False}


def element_commands(design, idx, ctx=None):
    """The instructions of one element (the design up to it, minus the design before it)."""
    before = len(commands({**design, "elements": design["elements"][:idx]}, ctx))
    return commands({**design, "elements": design["elements"][:idx + 1]}, ctx)[before:]


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
            on = repr(u if isinstance(u, tuple) else tuple(e["solid"]) if u == "solid" else u)
            lines.append(f"c.text({x}, {y}, {w}, {h}, {e['text']!r}, {e['font']!r}, {tuple(e['color'])}, {ALIGN.index(e['align'])}, {VALIGN.index(e['valign'])}, {on})")
        elif k == "icon":
            u = _under(e, els, i)
            on = repr(u if isinstance(u, tuple) else tuple(e["solid"]) if u == "solid" else u)
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
        elif k == "picture" and not int(e.get("radius", 0)):
            lines.append(f"c.picture({x}, {y}, MANIFEST['pictures'].index({e['picture']!r}))")
        elif k == "preview":
            lines.append(f"# 3D print preview ({VIEWS[e['view']]}): the printing screen does it like this (glass/app.py)")
            if e["view"] == "layers":
                lines.append(f"paths = a.api.preview({e['file'] or 'job'!r}, {e['layer'] if e['layer'] >= 0 else 'layer'}, 98, 70)   # [[points, level, printed], ...]")
                lines.append(f"draw_paths(c, {x}, {y}, paths, lambda k, q: T.PREVIEW_DONE if q[-1] else T.PREVIEW_TODO)   # drawn in a 98 x 70 box")
            elif e["view"] == "plate":
                lines.append(f"paths = a.api.model({e['file'] or 'job'!r}, 204, 88)['paths']   # [[points, level], ...]")
                lines.append(f"draw_paths(c, {x}, {y}, paths, lambda k, q: shade(q[1]))")
            else:
                lines.append(f"for ob in a.api.objects_preview({e['file'] or 'job'!r}, 204, 150)['objects']:")
                lines.append(f"    draw_paths(c, {x}, {y}, [(p, True) for p in ob['paths']], lambda i, q: T.TEAL_TEXT)")
        if k in ("ctext", "cimage") or (k in ("rect", "bar", "picture") and int(e.get("radius", 0))) or (k == "bar" and e.get("source", "fixed") != "fixed"):
            cmds = element_commands(design, i)
            if lines[-1].startswith(("c.fill(", "c.bar(", "c.picture(")) and k in ("rect", "bar", "picture"):
                lines.pop()   # replaced by the exact instructions below
            lines.append(f"# {KINDS[k][0]}: {len(cmds)} instructions" + (" (custom rendering: runs of fills)" if k in ("ctext", "cimage") else ""))
            if k in ("ctext", "cimage"):
                lines.append("for cmd in " + json.dumps(cmds) + ":\n    c._send(cmd)")
            else:
                lines += [f"c._send({cmd!r})" for cmd in cmds]
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
    t["Print status (live data)"] = {"wallpaper": wall, "elements": [
        new("panel", x=0, y=0, w=240, h=30, radius=0, edge=False),
        new("text", x=8, y=2, w=170, h=26, text="{state}", font="body"),
        new("text", x=176, y=2, w=58, h=26, text="{clock}", font="label", color=T.DIM, align="right"),
        new("panel", x=10, y=38, w=220, h=170),
        new("preview", x=16, y=44, w=208, h=130, view="layers", layer=-1),
        new("text", x=16, y=176, w=208, h=26, text="layer {layer}/{layers}  ·  z {z} mm", font="small", color=T.DIM, align="center"),
        new("panel", x=10, y=216, w=220, h=96, style="focus"),
        new("text", x=20, y=222, w=110, h=60, text="{progress}%", font="value"),
        new("text", x=124, y=226, w=98, h=22, text="{time_left} left", font="label", align="right"),
        new("text", x=124, y=250, w=98, h=20, text="done {done_at}", font="small", color=T.DIM, align="right"),
        new("bar", x=20, y=290, w=200, h=10, radius=5, source="progress")]}
    t["Custom font title"] = {"wallpaper": wall, "elements": [
        new("rect", x=20, y=70, w=200, h=120, radius=24, color=(18, 60, 58)),
        new("ctext", x=20, y=80, w=200, h=70, text="Ender", font_file=_any_font(), size=48, color=(153, 246, 228)),
        new("ctext", x=20, y=140, w=200, h=40, text="nozzle {nozzle}°", font_file=_any_font(), size=24, color=(236, 242, 245)),
        new("text", x=20, y=210, w=200, h=40, text="Any font on this PC, drawn as pixels", font="small", color=T.DIM, align="center")]}
    boot_bg = (8, 12, 15)   # the boot pictures' own background
    t["Splash"] = {"wallpaper": wall, "elements": [
        new("rect", x=0, y=0, w=240, h=320, color=boot_bg),
        new("picture", x=60, y=92, w=120, h=120, picture="boot_morph_7.png"),
        new("text", x=20, y=226, w=200, h=30, text="Ender Pearl", font="body", align="center", under="solid", solid=boot_bg)]}
    return t


def _any_font():
    for f in ("/usr/share/fonts/urw-base35/C059-Bold.otf", "/usr/share/fonts/dejavu-serif-fonts/DejaVuSerif-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/usr/share/fonts/liberation-serif-fonts/LiberationSerif-Bold.ttf"):
        if os.path.exists(f):
            return f
    return ""


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
        "Live data": "Text can show printer values that update by themselves: {nozzle}, {bed}, {progress}, {time_left}, "
                     "{layer}, {file}, {clock} and more (“Insert live data”). Progress bars can follow the print or the heating.",
        "3D print preview": "The same drawing the printing screen uses: the Pi turns the G-code's walls into an isometric "
                            "view and the display draws it as lines. Show the whole plate, the print built up to any layer "
                            "(follow the print, or scrub with the slider), or each object from above.",
        "Custom rendering": "Any font on this PC, and any picture, can be drawn too: they're turned into pixels here and "
                            "sent as rows of tiny filled boxes (about 0.25 ms each). Great for titles and logos; slower than "
                            "the built-in fonts, so the designer shows each element's cost.",
        "Needs a new firmware": "Only to make new wallpapers or icons part of the display itself (docs/06-design-and-assets.md). "
                                "Layouts, colours, texts, live data, previews and custom-rendered text and images never do.",
    }
