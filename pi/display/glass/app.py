"""Ender Loop glass UI for the printer display (our TJC firmware), all screens of design/MENUS.md.

Everything goes through the web server's API, so the display and the browser show the same state and every check
(bed clear, filament family, idle-only moves, override limits) stays in one place. Drawing goes through a Canvas
(canvas.py): TjcCanvas on the Pi, a Pillow canvas on the laptop for mockups, so both draw the same pixels.

Partial redraws: every screen draws named elements through App.el(key, signature, draw); an element is redrawn only
when its signature changes, which keeps the serial link quiet."""
import json
import os
import threading
import time

from . import theme as T
from .canvas import CENTER, LEFT, RIGHT

# ---------------------------------------------------------------- items and helpers


class Item:
    def __init__(self, icon, label, action=None, value=None, enabled=None, sub=False, danger=False, readonly=False):
        """readonly: an information row (normal colours, nothing happens on press)."""
        self.icon, self.label, self.action, self.value, self.enabled, self.sub, self.danger, self.readonly = icon, label, action, value, enabled, sub, danger, readonly

    def is_enabled(self):
        return self.enabled() if callable(self.enabled) else self.enabled is not False


def fmt_dur(s):
    if s is None:
        return "–"
    s = int(max(0, s)); h, m = divmod(s // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"


def wrap(text, width):
    out, line = [], ""
    for w in str(text).split():
        if len(line) + len(w) + (1 if line else 0) > width:
            out.append(line); line = w[:width]
        else:
            line = f"{line} {w}" if line else w[:width]
    return out + ([line] if line else [])


def ellipsize(s, n):
    s = str(s)
    return s if len(s) <= n else s[:n - 1] + "…"


# ---------------------------------------------------------------- widgets (drawn through the canvas)


def w_header(app, c, title, back):
    msg = app.toast_text()
    app.el("hdr", ("hdr",), lambda: (c.panel(0, 0, T.W, T.HEADER_H, r=0, edge=False), c.line(0, T.HEADER_H, T.W - 1, T.HEADER_H, (60, 120, 115))))
    t = msg[0] if msg else (("‹ " if back else "") + title)
    col = msg[1] if msg else T.TEXT
    t = fit(t, 176, "body")
    app.el("hdr-title", (t, col), lambda: c.text(8, 2, 180, T.HEADER_H - 4, t, "body", col, LEFT, 1, "glass"))
    clk = app.clock()
    link = app.link_ok()
    app.el("hdr-clock", (clk, link), lambda: (c.text(186, 2, 48, T.HEADER_H - 4, clk, "label", T.DIM if link else T.BAD, RIGHT, 1, "glass")))


with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "metrics.json")) as _f:
    METRICS = {k: v["widths"] for k, v in json.load(_f).items()}   # exact glyph advances of our TJC fonts (build_metrics.py)


def tw(s, font):
    """Pixel width of s in a TJC font (the display wraps text wider than its box, so everything is fitted)."""
    w = METRICS.get(font) or {}
    avg = (sum(w.values()) / len(w)) if w else 8
    return sum(w.get(ch, avg) for ch in str(s))


def fit(s, width, font):
    """s, shortened with "…" so it fits width pixels."""
    s = str(s)
    if tw(s, font) <= width:
        return s
    while s and tw(s + "…", font) > width:
        s = s[:-1]
    return s + "…"


def window(s, width, font, t):
    """Marquee: the part of s that fits, starting further in as time t (s) passes; pauses at both ends."""
    s = str(s)
    if tw(s, font) <= width:
        return s
    starts = [0]
    while tw(s[starts[-1]:], font) > width:
        starts.append(starts[-1] + 1)
    steps = len(starts)
    k = int(max(0.0, t - 1.0) / 0.22)                   # 1 s pause, then one character every 0.22 s
    k = k % (steps + 8)                                  # ~1.8 s pause at the end, then start over
    i = starts[min(k, steps - 1)]
    out = s[i:]
    while out and tw(out, font) > width:
        out = out[:-1]
    return out


def wrap_px(text, width, font):
    """Words into lines no wider than width pixels."""
    out, line = [], ""
    for w in str(text).split():
        cand = f"{line} {w}" if line else w
        if tw(cand, font) <= width:
            line = cand
        else:
            if line:
                out.append(line)
            line = fit(w, width, font)
    return out + ([line] if line else [])


def w_row(app, c, key, y, item, focus, x=T.PAD, w=T.W - 2 * T.PAD, since=0.0):
    en = item.is_enabled() or item.readonly
    val = item.value() if callable(item.value) else (item.value or "")
    font = "body" if focus else "label"
    right = x + w - (24 if item.sub else 8)
    valw = min(w - 90, int(tw(val, "label")) + 6) if val else 0
    labw = right - valw - (x + 36) - 6
    label = window(item.label, labw, font, time.time() - since) if focus else fit(item.label, labw, font)
    sig = (label, val, focus, en, item.sub)

    def draw():
        c.panel(x, y, w, T.ROW_H, focus=focus, r=8)
        on = "focus" if focus else "glass"
        icol = (T.FAINT if not en else (220, 255, 250) if focus else (T.BAD if item.danger else T.TEAL_TEXT))
        c.icon(x + 4, y, 28, T.ROW_H, item.icon, icol, "icon_s", on)
        tcol = T.FAINT if not en else (T.TEXT if focus else (205, 214, 218))
        c.text(x + 36, y, labw, T.ROW_H, label, font, tcol, LEFT, 1, on)
        if val:
            c.text(right - valw, y, valw, T.ROW_H, val, "label", (T.TEAL_TEXT if not item.readonly else T.TEXT) if en else T.FAINT, RIGHT, 1, on)
        if item.sub:
            c.icon(x + w - 24, y, 20, T.ROW_H, "next", T.DIM, "icon_s", on)
    app.el(key, sig, draw)


def w_tile(app, c, key, x, y, w, h, icon, label, focus, enabled=True):
    def draw():
        c.panel(x, y, w, h, focus=focus)
        on = "focus" if focus else "glass"
        col = T.FAINT if not enabled else ((220, 255, 250) if focus else T.TEAL_TEXT)
        c.icon(x, y + 6, w, h - 30, icon, col, "icon", on)
        c.text(x, y + h - 26, w, 20, label, "label", T.TEXT if focus else T.DIM, CENTER, 1, on)
    app.el(key, (icon, label, focus, enabled), draw)


def w_temp_card(app, c, key, x, y, w, icon, label, now, target):
    heating = target and now is not None and now < target - 2
    frac = 0 if not target else min(1.0, (now or 0) / target)

    box = app.el(key, (label,), lambda: (c.panel(x, y, w, 92), c.icon(x + 6, y + 6, 26, 24, icon, T.TEAL_TEXT, "icon_s"),
                                         c.text(x + 34, y + 6, w - 40, 24, label, "label", T.DIM)))
    val = "–" if now is None else f"{now:.0f}°"
    v = app.el(key + "/v", val, lambda: c.text(x + 10, y + 30, w - 20, 40, val, "value", T.TEXT), box)
    tgt = f"target {target:.0f}°" if target else "off"
    app.el(key + "/t", tgt, lambda: c.text(x + 10, y + 66, w - 20, 16, tgt, "small", T.DIM), box or v)   # the value box overlaps it
    app.el(key + "/b", (round(frac * (w - 25)), bool(heating)), lambda: c.bar(x + 12, y + 84, w - 24, 3, frac, T.WARN if heating else T.TEAL), box)


def w_button_pair(app, c, key, y, labels, focus):
    def draw():
        for i, lab in enumerate(labels):
            x = T.PAD + i * 114
            c.panel(x, y, 106, 40, focus=focus == i, r=8)
            c.text(x, y, 106, 40, lab, "body" if focus == i else "label", T.TEXT if focus == i else T.DIM, CENTER, 1, "focus" if focus == i else "glass")
    app.el(key, (tuple(labels), focus), draw)


def shade(level, done=True):
    """Height shading of the 3D previews: low layers dim, top layers bright teal; not yet printed = grey."""
    if not done:
        return T.PREVIEW_TODO
    lo, hi = (25, 95, 90), T.TEAL_TEXT
    return tuple(int(lo[k] + (hi[k] - lo[k]) * max(0.0, min(1.0, level))) for k in range(3))


def draw_paths(c, x, y, paths, color_of):
    """Polylines in box coordinates: (points, level[, done]); color_of(index, path) -> colour."""
    for k, p in enumerate(paths):
        col = color_of(k, p)
        pts = p[0]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            c.line(x + ax, y + ay, x + bx, y + by, col)


def preview_area(app, getter, empty="preview…"):
    """A top area for ListScreen: a glass panel with a model preview (paths from getter())."""
    def fn(c, x, y, w, h):
        paths = getter()
        if c is None:
            return (len(paths) if paths else 0, id(paths) if paths else 0)
        c.panel(x, y, w, h)
        if not paths:
            c.text(x, y, w, h, empty, "small", T.DIM, CENTER)
        else:
            draw_paths(c, x + 8, y + 6, paths, lambda k, p: shade(p[1] if len(p) > 1 and not isinstance(p[1], bool) else 1.0))
    return fn


# ---------------------------------------------------------------- screens


class Screen:
    title, back = "", True

    def __init__(self, app):
        self.app = app

    def draw(self, c):
        pass

    def turn(self, d):
        pass

    def press(self):
        pass

    def long_press(self):
        self.app.back()


class ListScreen(Screen):
    VISIBLE = 7

    def __init__(self, app, title, items_fn, back=True, top=None):
        """top: (height, draw(canvas, x, y, w, h) -> signature-or-None) drawn above the rows (e.g. a preview)."""
        super().__init__(app)
        self.title, self.items_fn, self.back, self.sel, self.top, self.top_area = title, items_fn, back, 0, 0, top
        self.since = time.time()       # when the current row got focus (its label starts scrolling after a pause)
        if top:
            self.VISIBLE = max(2, (T.H - T.HEADER_H - 8 - top[0] - 6) // (T.ROW_H + T.ROW_GAP))

    def items(self):
        return self.items_fn() if callable(self.items_fn) else self.items_fn

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, self.back)
        items = self.items()
        self.sel = max(0, min(self.sel, len(items) - 1))
        if self.sel < self.top:
            self.top = self.sel
        if self.sel >= self.top + self.VISIBLE:
            self.top = self.sel - self.VISIBLE + 1
        y0 = T.HEADER_H + 8
        if self.top_area:
            th, fn = self.top_area
            a.el("top", fn(None, T.PAD, y0, T.W - 2 * T.PAD, th), lambda: fn(c, T.PAD, y0, T.W - 2 * T.PAD, th))
            y0 += th + 6
        for i in range(self.VISIBLE):
            y = y0 + i * (T.ROW_H + T.ROW_GAP)
            k = self.top + i
            if k < len(items):
                w_row(a, c, f"row{i}", y, items[k], k == self.sel, since=self.since)
            else:
                a.el(f"row{i}", None, lambda y=y: c.background(T.PAD, y, T.W - 2 * T.PAD, T.ROW_H))
        if len(items) > self.VISIBLE:   # scroll bar
            h = self.VISIBLE * (T.ROW_H + T.ROW_GAP) - T.ROW_GAP
            th = max(18, h * self.VISIBLE // len(items)); ty = y0 + (h - th) * self.top // max(1, len(items) - self.VISIBLE)
            a.el("scroll", (ty, th), lambda: (c.background(T.W - 5, y0, 3, h), c.fill(T.W - 5, ty, 3, th, T.TEAL)))

    def turn(self, d):
        n = len(self.items())
        if n:
            old = self.sel
            self.sel = max(0, min(n - 1, self.sel + d))
            if self.sel != old:
                self.since = time.time()

    def press(self):
        items = self.items()
        if items and items[self.sel].is_enabled() and items[self.sel].action:
            items[self.sel].action()


class HomeScreen(Screen):
    title, back = "Ender Pearl", False
    TILES = [("print", "Print"), ("prepare", "Prepare"), ("control", "Control"), ("level", "Level")]

    def __init__(self, app):
        super().__init__(app)
        self.sel = 0

    def draw(self, c):
        a, st = self.app, self.app.state or {}
        w_header(a, c, self.title, False)
        t = a.temps()
        w_temp_card(a, c, "noz", 10, 38, 106, "nozzle", "Nozzle", t[0] if t else None, t[1] if t else 0)
        w_temp_card(a, c, "bed", 124, 38, 106, "bed", "Bed", t[2] if t else None, t[3] if t else 0)
        line, col = a.status_line()
        line = fit(line, 184, "label")
        box = a.el("status", (), lambda: c.panel(10, 138, 220, 34))
        a.el("status/t", line, lambda: c.text(20, 138, 186, 34, line, "label", T.TEXT), box)
        a.el("status/d", col, lambda: c.text(206, 138, 18, 34, "●", "label", col, CENTER), box)
        for i, (ic, lab) in enumerate(self.TILES):
            x, y = 10 + (i % 2) * 114, 180 + (i // 2) * 70
            w_tile(a, c, f"tile{i}", x, y, 106, 64, ic, lab, i == self.sel)

    def turn(self, d):
        self.sel = (self.sel + d) % 4

    def press(self):
        a = self.app
        [a.open_print, a.open_prepare, a.open_control, a.open_level][self.sel]()


class PrintingScreen(Screen):
    title, back = "Printing", False

    def __init__(self, app):
        super().__init__(app)
        self.sel = 0

    def tiles(self):
        paused = self.app.paused()
        return [("play" if paused else "pause", "Resume" if paused else "Pause"), ("gauge", "Tune"), ("stop", "Stop")]

    def draw(self, c):
        a = self.app
        p = a.progress()
        w_header(a, c, "Paused" if a.paused() else "Printing", False)
        box = a.el("card", (), lambda: c.panel(10, 36, 220, 96))
        f = fit(p["file"], 196, "small")
        a.el("card/f", f, lambda: c.text(20, 38, 200, 18, f, "small", T.DIM), box)
        num = str(int(p["pct"]))

        def pct():   # the number's box reaches past the widest "%" (3 digits), so a shorter number wipes the old one
            c.text(16, 52, 120, 60, num, "big", T.TEXT)
            c.text(16 + tw(num, "big") + 3, 70, 30, 30, "%", "body", T.TEAL_TEXT)   # real glyph widths: "100" is 87 px
        big = a.el("card/p", num, pct, box)
        left, done, el = f"{fmt_dur(p['left'])} left", f"done {p['done_at']}", f"elapsed {fmt_dur(p['elapsed'])}"
        a.el("card/l", left, lambda: c.text(120, 56, 104, 18, left, "label", T.TEXT, RIGHT), box or big)   # overlaps the number box
        a.el("card/d", done, lambda: c.text(120, 76, 104, 18, done, "small", T.DIM, RIGHT), box or big)
        a.el("card/e", el, lambda: c.text(120, 94, 104, 18, el, "small", T.DIM, RIGHT), box or big)
        a.el("card/b", round(p["pct"] * 2), lambda: c.bar(20, 118, 200, 5, p["pct"] / 100), box)
        prev = a.preview()

        def preview():
            c.panel(10, 138, 106, 92)
            x0, y0, w, h = 14, 142, 98, 70
            paths = sorted(prev["paths"], key=lambda q: bool(q[-1]))     # grey still-to-print first, printed on top
            draw_paths(c, x0, y0, paths, lambda k, q: T.PREVIEW_DONE if q[-1] else T.PREVIEW_TODO)   # printed so far = teal
            c.text(14, 212, 98, 16, f"L {p['layer']}/{p['layers']}  z{p['z']:.1f}", "small", T.DIM, CENTER)
        a.el("preview", (prev["key"], len(prev["paths"]), p["layer"]), preview)   # redraw when the paths arrive
        d = a.details()

        rows = [("nozzle", d["noz"]), ("bed", d["bed"]), ("fan", d["fan"]), ("speed", d["speed"]), ("flow", d["flow"])]
        box = a.el("details", (), lambda: (c.panel(124, 138, 106, 92),
                                           [c.icon(128, 142 + i * 17, 18, 17, ic, T.TEAL_TEXT, "icon_s") for i, (ic, _) in enumerate(rows)]))
        for i, (ic, v) in enumerate(rows):
            a.el(f"details/{i}", v, lambda i=i, v=v: c.text(148, 142 + i * 17, 78, 17, v, "small", T.TEXT), box)
        for i, (ic, lab) in enumerate(self.tiles()):
            w_tile(a, c, f"ptile{i}", 10 + i * 75, 236, 70, 78, ic, lab, i == self.sel)

    def turn(self, d):
        self.sel = (self.sel + d) % 3

    def press(self):
        a = self.app
        if self.sel == 0:
            a.pause_resume()
        elif self.sel == 1:
            a.open_tune()
        else:
            a.open_stop()


class SkipScreen(Screen):
    title = "Skip an object"

    def __init__(self, app):
        super().__init__(app)
        self.sel, self.data = 0, None
        threading.Thread(target=self._load, daemon=True).start()

    def _load(self):
        st = self.app.state or {}
        try:
            self.data = self.app.api.objects_preview(st.get("job"), 204, 150)
        except Exception as e:
            self.data = {"objects": [], "error": str(e)}

    def objects(self):
        return (self.data or {}).get("objects") or []

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, True)
        objs = self.objects()
        dropped = set(((a.state or {}).get("status") or {}).get("dropped") or [])
        n = len(objs)
        self.sel = max(0, min(self.sel, n - 1)) if n else 0

        def preview():
            c.panel(10, 38, 220, 166)
            if not objs:
                c.text(10, 38, 220, 166, (self.data or {}).get("error") or "loading objects…", "small", T.DIM, CENTER)
                return
            for k, o in enumerate(objs):
                col = (T.BAD if o["name"] in dropped else T.TEAL_TEXT if k == self.sel else T.PREVIEW_TODO)
                draw_paths(c, 18, 46, [(p, True) for p in o["paths"]], lambda i, q, col=col: col)
        a.el("pv", (n, self.sel, tuple(sorted(dropped)), (self.data or {}).get("error")), preview)
        name = objs[self.sel]["name"].split(" id:")[0] if objs else ""
        state = "already skipped" if objs and objs[self.sel]["name"] in dropped else f"object {self.sel + 1} of {n}" if n else ""
        name = fit(name, 200, "body")
        a.el("name", (name, state), lambda: (c.panel(10, 210, 220, 50), c.text(18, 212, 204, 26, name, "body", T.TEXT, CENTER),
                                              c.text(18, 236, 204, 20, state, "small", T.DIM, CENTER)))
        a.el("hint", (1,), lambda: (c.panel(10, 266, 220, 46), c.text(10, 266, 220, 24, "turn to choose · press to skip", "small", T.DIM, CENTER),
                                     c.text(10, 286, 220, 22, "hold to go back", "small", T.FAINT, CENTER)))

    def turn(self, d):
        n = len(self.objects())
        if n:
            self.sel = (self.sel + d) % n

    def press(self):
        objs = self.objects()
        if not objs:
            return
        o = objs[self.sel]["name"]
        if o in set(((self.app.state or {}).get("status") or {}).get("dropped") or []):
            return self.app.toast("already skipped", T.WARN)
        a = self.app
        a.confirm("Skip object", f"Stop printing {o.split(' id:')[0]} from the next layer? The other objects carry on.", "Skip",
                  lambda: a.run("Skip", lambda: a.api.cmd(f"drop {o}")), danger=True)


class SplashScreen(Screen):
    """Boot: the infinity mark rotates upright, gains its flat caps (Ender Pearl logo), moves up, the name appears.
    frames: picture ids from the manifest ("boot"); played once, then Home."""
    back = False

    def __init__(self, app, boot, then):
        super().__init__(app)
        self.boot, self.then, self.i, self.t0 = boot, then, 0, time.time()

    def draw(self, c):
        b = self.boot
        steps = b["rotate"] + b["morph"]
        k = int((time.time() - self.t0) / b.get("dt", 0.06))
        if k < len(steps):
            c.picture(b["x"], b["y"], steps[k])
        elif k < len(steps) + b["rise"]:
            j = k - len(steps) + 1
            y = b["y"] - j * b["dy"]
            c.fill(b["x"], y + b["size"], b["size"], b["dy"] + 2, b["bg"])
            c.picture(b["x"], y, steps[-1])
        elif k < len(steps) + b["rise"] + len(b["text"]):
            c.picture(b["tx"], b["ty"], b["text"][k - len(steps) - b["rise"]])
        else:
            self.then()

    def long_press(self):
        self.then()


class ValueScreen(Screen):
    def __init__(self, app, title, icon, value, lo, hi, step, unit, commit, fmt="{:.0f}"):
        super().__init__(app)
        self.title, self.icon, self.v, self.lo, self.hi, self.step, self.unit, self.commit, self.fmt = title, icon, value, lo, hi, step, unit, commit, fmt

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, True)
        v = self.fmt.format(self.v)

        def big():
            c.panel(10, 46, 220, 150, focus=True)
            c.icon(10, 54, 220, 30, self.icon, (220, 255, 250), "icon", "focus")
            c.text(10, 86, 220, 56, v, "value", T.TEXT, CENTER, 1, "focus")
            c.text(10, 140, 220, 22, self.unit, "label", T.TEAL_TEXT, CENTER, 1, "focus")
            frac = (self.v - self.lo) / (self.hi - self.lo) if self.hi > self.lo else 0
            c.bar(30, 172, 180, 4, frac)
        a.el("big", (v,), big)
        a.el("hint", (self.lo, self.hi), lambda: (c.panel(10, 206, 220, 70),
              c.text(10, 212, 220, 20, f"{self.fmt.format(self.lo)} – {self.fmt.format(self.hi)} {self.unit}", "label", T.DIM, CENTER),
              c.text(10, 234, 220, 18, "turn to change · press to set", "small", T.DIM, CENTER),
              c.text(10, 252, 220, 18, "hold to cancel", "small", T.FAINT, CENTER)))

    def turn(self, d):
        self.v = round(max(self.lo, min(self.hi, self.v + d * self.step)), 4)

    def press(self):
        v = self.v
        self.app.back()
        self.app.run(f"{self.title}: {self.fmt.format(v)} {self.unit}", lambda: self.commit(v))


class ConfirmScreen(Screen):
    def __init__(self, app, title, text, yes, on_yes, danger=False):
        super().__init__(app)
        self.title, self.text_, self.yes, self.on_yes, self.danger, self.sel = title, text, yes, on_yes, danger, 0

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, True)
        lines = wrap_px(self.text_, 196, "label")[:7]
        a.el("msg", tuple(lines), lambda: (c.panel(10, 46, 220, 200),
              c.icon(10, 54, 220, 34, "alert" if self.danger else "info", T.WARN if self.danger else T.TEAL_TEXT, "icon"),
              [c.text(20, 92 + i * 21, 200, 21, ln, "label", T.TEXT, CENTER) for i, ln in enumerate(lines)]))
        w_button_pair(a, c, "btn", 264, ["Cancel", self.yes], self.sel)

    def turn(self, d):
        self.sel = 1 if d > 0 else 0

    def press(self):
        self.app.back()
        if self.sel == 1:
            self.on_yes()


class MessageScreen(Screen):
    def __init__(self, app, title, text, color=T.TEXT, icon="info"):
        super().__init__(app)
        self.title, self.text_, self.color, self.icon = title, text, color, icon

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, True)
        lines = wrap_px(self.text_, 196, "label")[:8]
        a.el("msg", tuple(lines), lambda: (c.panel(10, 46, 220, 200), c.icon(10, 54, 220, 34, self.icon, self.color, "icon"),
              [c.text(20, 92 + i * 20, 200, 20, ln, "label", T.TEXT, CENTER) for i, ln in enumerate(lines)]))
        a.el("ok", (1,), lambda: (c.panel(67, 264, 106, 40, focus=True, r=8), c.text(67, 264, 106, 40, "OK", "body", T.TEXT, CENTER, 1, "focus")))

    def press(self):
        self.app.back()


class JogScreen(Screen):
    def __init__(self, app, axis, step):
        super().__init__(app)
        self.title, self.axis, self.step, self.pending, self.pos, self.lock = f"Move {axis}", axis, step, 0.0, None, threading.Lock()
        threading.Thread(target=self._sender, daemon=True).start()

    def _sender(self):
        while self.app.screen is self or self.pending:
            time.sleep(0.25)
            with self.lock:
                d, self.pending = round(self.pending, 3), 0.0
            if d:
                lim = 10 if self.axis == "Z" else 100
                try:
                    r = self.app.api.printer("jog", axis=self.axis, dist=max(-lim, min(lim, d)))
                    self.pos = (r or {}).get("pos") or self.pos
                except Exception as e:
                    self.app.toast(str(e), T.BAD)

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, True)
        i = "XYZ".index(self.axis)
        v = "–" if not self.pos else f"{self.pos[i]:.2f}"
        a.el("big", (v,), lambda: (c.panel(10, 46, 220, 150, focus=True), c.icon(10, 54, 220, 30, "move", (220, 255, 250), "icon", "focus"),
              c.text(10, 86, 220, 56, v, "value", T.TEXT, CENTER, 1, "focus"), c.text(10, 140, 220, 22, f"{self.axis} position (mm)", "label", T.TEAL_TEXT, CENTER, 1, "focus")))
        a.el("hint", (self.step,), lambda: (c.panel(10, 206, 220, 70), c.text(10, 212, 220, 20, f"{self.step:g} mm per click", "label", T.DIM, CENTER),
              c.text(10, 234, 220, 18, "turn to move · press when done", "small", T.DIM, CENTER),
              c.text(10, 252, 220, 18, "home first after switching on", "small", T.FAINT, CENTER)))

    def turn(self, d):
        with self.lock:
            self.pending += d * self.step

    def press(self):
        self.app.back()


class MeshScreen(Screen):
    title = "Bed mesh"

    def press(self):
        self.app.back()

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, True)
        m = a.mesh
        grid = (m or {}).get("grid") or []
        a.el("mesh", (str(grid),), lambda: self._draw(c, grid))

    def _draw(self, c, grid):
        c.panel(10, 40, 220, 270)
        if not grid:
            c.text(10, 140, 220, 24, "reading the mesh…", "label", T.DIM, CENTER)
            return
        n = len(grid); vals = [v for row in grid for v in row]
        lo, hi = min(vals), max(vals); span = max(1e-6, hi - lo)
        cw = 200 // n
        for j, row in enumerate(reversed(grid)):     # back row on top
            for i, v in enumerate(row):
                t = (v - lo) / span
                col = (int(30 + 200 * t), int(140 + 60 * (1 - abs(t - 0.5) * 2)), int(200 - 160 * t))
                x, y = 20 + i * cw, 50 + j * cw
                c.fill(x + 1, y + 1, cw - 2, cw - 2, col)
                c.text(x, y, cw, cw, f"{v:+.2f}", "small", (10, 14, 16), CENTER, 1, col)
        c.text(10, 262, 220, 20, f"range {hi - lo:.2f} mm", "label", T.TEXT, CENTER)
        c.text(10, 284, 220, 18, "front at the bottom · press to go back", "small", T.DIM, CENTER)


class BusyScreen(Screen):
    def __init__(self, app, title, text):
        super().__init__(app)
        self.title, self.text_, self.t0 = title, text, time.time()

    def draw(self, c):
        a = self.app
        w_header(a, c, self.title, False)
        dots = "." * (1 + int(time.time() - self.t0) % 3)
        a.el("busy", (self.text_, dots), lambda: (c.panel(10, 90, 220, 120), c.icon(10, 104, 220, 34, "spinner", T.TEAL_TEXT, "icon"),
              c.text(10, 146, 220, 24, self.text_ + dots, "label", T.TEXT, CENTER), c.text(10, 172, 220, 20, fmt_dur(time.time() - self.t0), "small", T.DIM, CENTER)))

    def long_press(self):
        pass


# ---------------------------------------------------------------- the app


class App:
    def __init__(self, api, canvas, wallpapers, config=None):
        self.api, self.c, self.wallpapers = api, canvas, wallpapers
        self.cfg = {"wallpaper": next(iter(wallpapers)), "brightness": 80, "sleep_s": 300, "clock24": True, **(config or {})}
        self.state, self.state_err, self.state_t = None, None, 0
        self.stack, self.cache, self.msg = [], {}, None
        self.busy, self.mesh, self.plan, self.plan_name, self.prev_cache = None, None, None, None, {}
        self.last_input, self.dimmed, self.lock = time.time(), False, threading.RLock()
        self.was_printing = False
        self.set_wallpaper(self.cfg["wallpaper"], redraw=False)
        self.stack.append(HomeScreen(self))

    # ---- navigation ----
    @property
    def screen(self):
        return self.stack[-1]

    def push(self, s):
        with self.lock:
            self.stack.append(s); self.cache = {}

    def back(self):
        with self.lock:
            if len(self.stack) > 1:
                self.stack.pop(); self.cache = {}

    def home(self):
        with self.lock:
            del self.stack[1:]; self.cache = {}

    def menu(self, title, items):
        self.push(ListScreen(self, title, items))

    def confirm(self, title, text, yes, on_yes, danger=False):
        self.push(ConfirmScreen(self, title, text, yes, on_yes, danger))

    def toast(self, text, color=T.TEAL_TEXT, secs=4):
        self.msg = (text, color, time.time() + secs)

    def toast_text(self):
        m = self.msg
        return (m[0], m[1]) if m and time.time() < m[2] else None

    def set_wallpaper(self, name, redraw=True):
        if name not in self.wallpapers:
            return
        self.cfg["wallpaper"] = name
        self.c.pics = self.wallpapers[name]
        if redraw:
            self.cache = {}

    # ---- background work ----
    def run(self, label, fn, then=None, busy=None):
        """An API call in the background; the header shows progress and the result. busy: show a busy screen."""
        if self.busy:
            return self.toast("busy: wait for the last action", T.WARN)
        self.busy = label
        self.toast(label + "…", T.DIM, 900)
        if busy:
            self.push(BusyScreen(self, label, busy))

        def work():
            try:
                r = fn()
                if busy:
                    self.back()
                self.toast(f"{label}: done", T.GOOD)
                if then:
                    then(r)
            except Exception as e:
                if busy:
                    self.back()
                self.msg = None
                self.push(MessageScreen(self, "Not done", str(e), T.BAD, "alert"))
            finally:
                self.busy = None
                self.state_t = 0
        threading.Thread(target=work, daemon=True).start()

    def refresh(self):
        try:
            self.state, self.state_err = self.api.state(), None
        except Exception as e:
            self.state_err = str(e) or "server not reachable"
        self.state_t = time.time()
        printing = self.printing()
        if printing and not isinstance(self.stack[0], PrintingScreen):
            self.stack[:] = [PrintingScreen(self)]; self.cache = {}
            self.wake()                            # a print started: show it
        elif not printing and isinstance(self.stack[0], PrintingScreen):
            self.stack[:] = [HomeScreen(self)]; self.cache = {}
            self.wake()
            st = (self.state or {}).get("status") or {}
            if st.get("state") == "done":
                self.push(MessageScreen(self, "Print finished", f"{st.get('file', '')} finished. Clear the bed before the next print.", T.GOOD, "check2"))
        try:
            dc = self.api.display_config()
            if dc:
                self.apply_config(dc)
        except Exception:
            pass

    def apply_config(self, dc):
        if dc.get("wallpaper") and dc["wallpaper"] != self.cfg["wallpaper"]:
            self.set_wallpaper(dc["wallpaper"])
        if "brightness" in dc and dc["brightness"] != self.cfg.get("brightness"):
            self.cfg["brightness"] = dc["brightness"]
            if not self.dimmed:
                self.c.brightness(dc["brightness"])   # changed in the web UI
        for k in ("sleep_s", "clock24"):
            if k in dc:
                self.cfg[k] = dc[k]
        m, sh = dc.get("message"), dc.get("show")
        if "message_id" not in self.cfg:          # first sync: don't replay what was sent before the app started
            self.cfg["message_id"] = (m or {}).get("id")
            self.cfg["show_id"] = (sh or {}).get("id")
            return
        if m and m.get("id") != self.cfg.get("message_id"):
            self.cfg["message_id"] = m.get("id")
            self.push(MessageScreen(self, "Message", m.get("text", ""), T.TEAL_TEXT, "message"))
            self.wake()
        if sh and sh.get("id") != self.cfg.get("show_id"):   # "show this screen" from the web UI
            self.cfg["show_id"] = sh.get("id")
            self.wake()
            if not self.printing():
                self.home()
                {"print": self.open_print, "prepare": self.open_prepare, "control": self.open_control, "level": self.open_level}.get(sh.get("screen"), lambda: None)()

    # ---- state helpers ----
    def printing(self):
        return bool(self.state and (self.state.get("printing") or self.state.get("sd")))

    def paused(self):
        st = self.state or {}
        return ((st.get("status") or {}).get("state") == "paused") or bool((st.get("sd") or {}).get("paused"))

    def temps(self):
        st = self.state
        if not st:
            return None
        if st.get("printing") and st.get("status"):
            return st["status"].get("temps")
        return st.get("idle_temps")

    def link_ok(self):
        return not self.state_err

    def clock(self):
        return time.strftime("%H:%M" if self.cfg.get("clock24", True) else "%I:%M")

    def status_line(self):
        st = self.state
        if self.state_err:
            return "Server not reachable", T.BAD
        if not st:
            return "Connecting…", T.DIM
        q = st.get("queue") or {}
        al = q.get("alert")
        if isinstance(al, dict):     # the server's alert record: {"text", "kind", "acked", ...}; acknowledged ones stay quiet
            al = None if al.get("acked") else al.get("text")
        if al:
            return ellipsize(str(al), 26), T.WARN
        if not self.temps():
            return "Printer not connected", T.WARN
        rec = st.get("filament")
        if rec and not rec.get("family"):
            return "Idle  ·  No filament", T.WARN       # unloaded
        return f"Idle  ·  {(rec or {}).get('family', '?')} loaded", T.TEAL

    def progress(self):
        st = self.state or {}
        s = st.get("status") or {}
        if st.get("sd"):
            sd = st["sd"]
            pct = 100.0 * sd.get("done", 0) / sd["size"] if sd.get("size") else 0
            return {"file": sd.get("file") or "SD card", "pct": pct, "left": None, "done_at": "–", "elapsed": 0, "layer": 0, "layers": 0, "z": 0.0}
        left = s.get("remaining")
        if left is not None:
            left = max(0, left - (time.time() - s.get("updated", time.time())))
        done_at = time.strftime("%H:%M", time.localtime(s["finish_at"])) if s.get("finish_at") else "–"
        el = time.time() - s["started"] if s.get("started") else 0
        # by time, like the phone notifications: lines sent ran far ahead (the small top layers are <1 % of the lines)
        if left is not None and el > 0:
            pct = 100.0 * el / (el + left)
        else:
            pct = 100.0 * s.get("sent", 0) / s["total"] if s.get("total") else 0
        pct = 100.0 if s.get("state") == "done" else min(pct, 99.0)   # 100 % only once it has finished
        return {"file": st.get("job") or s.get("file") or "", "pct": pct, "left": left, "done_at": done_at, "elapsed": el,
                "layer": s.get("layer", -1) + 1, "layers": s.get("layers", 0), "z": s.get("z") or 0.0}

    def details(self):
        st = self.state or {}
        s = st.get("status") or {}
        t = self.temps() or [0, 0, 0, 0]
        ov = s.get("overrides") or {}
        fan = ov.get("fan")
        if fan is None and self.plan and s.get("layer", -1) >= 0:
            lf = self.plan.get("layer_fan") or []
            fan = lf[min(len(lf) - 1, s["layer"])] if lf else None
        return {"noz": f"{t[0]:.0f} / {t[1]:.0f}°", "bed": f"{t[2]:.0f} / {t[3]:.0f}°",
                "fan": "–" if fan is None else f"{fan:.0f}%", "speed": f"{ov.get('speed', 1) * 100:.0f}% speed",
                "flow": f"{ov.get('flow', 1) * 100:.0f}% flow"}

    def preview(self):
        st = self.state or {}
        s = st.get("status") or {}
        name, n = st.get("job"), s.get("layer", -1)
        if not name or n < 0:
            return {"key": None, "paths": []}
        key = (name, n)
        if key not in self.prev_cache:
            self.prev_cache.clear()
            self.prev_cache[key] = {"key": key, "paths": []}

            def load():
                try:
                    if self.plan_name != name:
                        self.plan, self.plan_name = self.api.plan(name), name
                    self.prev_cache[key] = {"key": key, "paths": self.api.preview(name, n, 98, 70)}
                except Exception:
                    pass
            threading.Thread(target=load, daemon=True).start()
        return self.prev_cache[key]

    # ---- actions ----
    def pause_resume(self):
        st = self.state or {}
        if st.get("sd"):
            a = "sd_resume" if self.paused() else "sd_pause"
            return self.run("Resume" if self.paused() else "Pause", lambda: self.api.printer(a))
        self.run("Resume" if self.paused() else "Pause", lambda: self.api.cmd("resume" if self.paused() else "pause"))

    def stop_print(self):
        if (self.state or {}).get("sd"):
            return self.run("Stop", lambda: self.api.printer("sd_stop"))
        self.run("Stop", self.api.stop)

    # ---- menus (design/MENUS.md) ----
    def idle(self):
        return not self.printing() and not self.busy

    def open_print(self):
        self.menu("Print", [Item("back", "Back", self.back), Item("folder", "From the Pi", self.open_files, sub=True),
                            Item("sd", "From the SD card", self.open_sd, sub=True), Item("queue", "Print queue", self.open_queue, sub=True)])

    def open_files(self):
        box = {"files": None, "err": None}

        def load():
            try:
                box["files"] = self.api.files()
            except Exception as e:
                box["err"] = str(e)
        threading.Thread(target=load, daemon=True).start()

        def items():
            out = [Item("back", "Back", self.back)]
            if box["err"]:
                return out + [Item("alert", ellipsize(box["err"], 24), readonly=True)]
            if box["files"] is None:
                return out + [Item("spinner", "Loading…", readonly=True)]
            if not box["files"]:
                return out + [Item("file", "No G-code files yet", readonly=True)]
            return out + [Item("file", f["name"].rsplit(".", 1)[0], lambda f=f: self.open_file(f),   # newest first; the value is the print time
                               value=f.get("estimate") or "–", sub=True) for f in box["files"][:60]]
        self.menu("From the Pi", items)

    def open_file(self, f):
        box = {"plan": None, "pv": None}

        def load():
            try:
                box["plan"] = self.api.plan(f["name"])
            except Exception:
                box["plan"] = {}
            try:
                box["pv"] = self.api.model_preview(f["name"], 204, 88)
            except Exception:
                box["pv"] = []
        threading.Thread(target=load, daemon=True).start()

        def items():
            p = box["plan"] or {}
            mat = ((p.get("settings") or {}).get("material") or "?").replace("_loop", "").upper()
            return [Item("back", "Back", self.back),
                    Item("play", "Start print", lambda: self.confirm("Start print", f"Print {f['name']}? Check the bed is clear and {mat} is loaded.",
                                                                    "Print", lambda: self.run("Start print", lambda: self.api.print_file(f["name"]), then=lambda r: self.home())),
                         enabled=self.idle),
                    Item("timer", "Time", value=p.get("estimate", "…") if p else "…", enabled=True),
                    Item("filament", "Filament", value=f"{p['filament_m']:.1f} m" if p.get("filament_m") else "…"),
                    Item("layers", "Layers", value=str(p.get("layers", "…"))),
                    Item("flow", "Material", value=mat),
                    Item("clock", "Modified", value=time.strftime("%b %d %H:%M", time.localtime(f["mtime"])), readonly=True)]
        self.push(ListScreen(self, ellipsize(f["name"].rsplit(".", 1)[0], 20), items, top=(100, preview_area(self, lambda: box["pv"]))))

    def open_sd(self):
        box = {"files": None, "err": None}

        def load():
            try:
                box["files"] = list(reversed(self.api.sd_list()))   # newest first by card order (no dates from the firmware)
            except Exception as e:
                box["err"] = str(e)
        threading.Thread(target=load, daemon=True).start()

        def items():
            out = [Item("back", "Back", self.back)]
            if box["err"]:
                return out + [Item("alert", ellipsize(box["err"], 24), readonly=True)]
            if box["files"] is None:
                return out + [Item("spinner", "Reading the card…", readonly=True)]
            return out + [Item("sd", ellipsize(f.get("long") or f["name"], 17), lambda f=f: self.open_sd_file(f),
                               value=f"{(f.get('size') or 0) / 1e6:.1f} MB", sub=True) for f in box["files"][:80]]
        self.menu("SD card", items)

    def open_sd_file(self, f):
        name = f.get("long") or f["name"]
        self.menu(ellipsize(name, 20), [
            Item("back", "Back", self.back),
            Item("play", "Start SD print", lambda: self.confirm("SD print", f"Print {name} from the printer's card? Check the bed is clear.", "Print",
                                                              lambda: self.run("SD print", lambda: self.api.printer("sd_print", name=f["name"], bed_clear=True), then=lambda r: self.home())),
                 enabled=self.idle),
            Item("cancel", "Delete from card", lambda: self.confirm("Delete", f"Delete {name} from the SD card?", "Delete",
                                                                     lambda: self.run("Delete", lambda: self.api.printer("sd_delete", name=f["name"]), then=lambda r: self.back()), danger=True),
                 enabled=self.idle, danger=True),
            Item("hourglass", "Size", value=f"{(f.get('size') or 0) / 1e6:.1f} MB")])

    def open_queue(self):
        box = {"q": None}

        def load():
            try:
                box["q"] = self.api.queue()
            except Exception:
                box["q"] = {"items": []}
        threading.Thread(target=load, daemon=True).start()

        def items():
            q = box["q"]
            out = [Item("back", "Back", self.back)]
            if q is None:
                return out + [Item("spinner", "Loading…", readonly=True)]
            pending = [x for x in q.get("items", []) if x.get("status") != "done"]
            if pending:
                out.append(Item("play", "Start queue" if not q.get("waiting") else "Bed is clear: next",
                                lambda: self.confirm("Queue", "Start the next queued job? Check the bed is clear.", "Start",
                                                     lambda: self.run("Queue", lambda: self.api.queue_op("start", bed_clear=True), then=lambda r: self.home())),
                                enabled=self.idle))
            return out + [Item("file", ellipsize(x["name"].rsplit(".", 1)[0], 17), value=f"{x.get('done', 0)}/{x.get('copies', 1)}", readonly=True) for x in pending] \
                or out + [Item("queue", "Queue is empty", readonly=True)]
        self.menu("Print queue", items)

    def open_tune(self):
        st = self.state or {}
        ov = (st.get("status") or {}).get("overrides") or {}
        t = self.temps() or [0, 0, 0, 0]
        sd = bool(st.get("sd"))
        if sd:
            send = lambda **kw: self.api.printer("sd_tune", **kw)
            items = [Item("back", "Back", self.back),
                     Item("nozzle", "Nozzle", lambda: self.push(ValueScreen(self, "Nozzle", "nozzle", round(t[1]), 0, 260, 1, "°C", lambda v: send(nozzle=v))), value=f"{t[1]:.0f}°"),
                     Item("bed", "Bed", lambda: self.push(ValueScreen(self, "Bed", "bed", round(t[3]), 0, 100, 1, "°C", lambda v: send(bed=v))), value=f"{t[3]:.0f}°"),
                     Item("fan", "Fan", lambda: self.push(ValueScreen(self, "Fan", "fan", 100, 0, 100, 5, "%", lambda v: send(fan=v)))),
                     Item("speed", "Speed", lambda: self.push(ValueScreen(self, "Speed", "speed", 100, 50, 150, 5, "%", lambda v: send(speed=v)))),
                     Item("flow", "Flow", lambda: self.push(ValueScreen(self, "Flow", "flow", 100, 80, 120, 1, "%", lambda v: send(flow=v))))]
            return self.menu("Tune", items)
        cmd = self.api.cmd
        items = [Item("back", "Back", self.back),
                 Item("speed", "Speed", lambda: self.push(ValueScreen(self, "Speed", "speed", round(ov.get("speed", 1) * 100), 50, 150, 5, "%", lambda v: cmd(f"speed {v / 100:g}"))), value=f"{ov.get('speed', 1) * 100:.0f}%"),
                 Item("flow", "Flow", lambda: self.push(ValueScreen(self, "Flow", "flow", round(ov.get("flow", 1) * 100), 80, 120, 1, "%", lambda v: cmd(f"flow {v / 100:g}"))), value=f"{ov.get('flow', 1) * 100:.0f}%"),
                 Item("fan", "Fan", lambda: self.push(ValueScreen(self, "Fan", "fan", round(ov.get("fan", 100)), 0, 100, 5, "%", lambda v: cmd(f"fan {v:g}")))),
                 Item("nozzle", "Nozzle", lambda: self.push(ValueScreen(self, "Nozzle", "nozzle", round(t[1]), 0, 260, 1, "°C", lambda v: cmd(f"temp {v:g}"))), value=f"{t[1]:.0f}°"),
                 Item("bed", "Bed", lambda: self.push(ValueScreen(self, "Bed", "bed", round(t[3]), 0, 100, 1, "°C", lambda v: cmd(f"bed {v:g}"))), value=f"{t[3]:.0f}°"),
                 Item("zoffset", "Z babystep", lambda: self.push(ValueScreen(self, "Z babystep", "zoffset", 0.0, -0.2, 0.2, 0.01, "mm", lambda v: cmd(f"babystep {v:g}"), "{:+.2f}")),
                      value=f"{ov.get('babystep', 0):+.2f}"),
                 Item("skip", "Skip an object", self.open_skip, sub=True)]
        self.menu("Tune", items)

    def open_skip(self):
        self.push(SkipScreen(self))

    def open_stop(self):
        sd = bool((self.state or {}).get("sd"))
        objs = ((self.state or {}).get("status") or {}).get("objects") or []
        self.menu("Stop", [Item("back", "Back", self.back),
                           Item("skip", "Skip an object", self.open_skip, sub=True, enabled=not sd and len(objs) > 1),
                           Item("stop", "Stop print", lambda: self.confirm("Stop print", "Stop this print? It can't be resumed.", "Stop", self.stop_print, danger=True), danger=True)])

    def open_prepare(self):
        t = lambda i: (self.temps() or [0, 0, 0, 0])[i]
        p = self.api.printer
        self.menu("Prepare", lambda: [
            Item("back", "Back", self.back),
            Item("home", "Home axes", lambda: self.menu("Home axes", [Item("back", "Back", self.back)] + [
                Item("home", lab, lambda ax=ax, lab=lab: self.run(f"Home {lab.lower()}", lambda: p("home", timeout=200, axes=ax), busy="Homing"), enabled=self.idle)
                for lab, ax in (("All axes", ""), ("X", "X"), ("Y", "Y"), ("Z", "Z"))]), sub=True, enabled=self.idle),
            Item("move", "Move axes", self.open_move, sub=True, enabled=self.idle),
            Item("heat", "Preheat", lambda: self.menu("Preheat", [Item("back", "Back", self.back),
                Item("heat", "PLA", lambda: self.run("Preheat PLA", lambda: p("preheat", material="pla_loop"))),
                Item("heat", "PETG", lambda: self.run("Preheat PETG", lambda: p("preheat", material="petg_loop")))]), sub=True, enabled=self.idle),
            Item("cool", "Cool down", lambda: self.run("Cool down", lambda: p("cooldown")), enabled=self.idle),
            Item("nozzle", "Nozzle temperature", lambda: self.push(ValueScreen(self, "Nozzle", "nozzle", round(t(1)), 0, 260, 5, "°C", lambda v: p("temps", nozzle=v))), value=f"{t(0):.0f}°", enabled=self.idle),
            Item("bed", "Bed temperature", lambda: self.push(ValueScreen(self, "Bed", "bed", round(t(3)), 0, 100, 5, "°C", lambda v: p("temps", bed=v))), value=f"{t(2):.0f}°", enabled=self.idle),
            Item("fan", "Fan", lambda: self.push(ValueScreen(self, "Fan", "fan", 0, 0, 100, 10, "%", lambda v: p("fan", percent=v))), enabled=self.idle),
            Item("filament", "Filament", self.open_filament, sub=True, enabled=self.idle),
            Item("park", "Park head", lambda: self.run("Park", lambda: p("park", timeout=60)), enabled=self.idle),
            Item("motors", "Motors off", lambda: self.run("Motors off", lambda: p("motors_off")), enabled=self.idle)])

    def open_move(self):
        self.menu("Move axes", [Item("back", "Back", self.back)] + [
            Item("move", f"Move {ax}", lambda ax=ax: self.menu(f"Move {ax}: step", [Item("back", "Back", self.back)] + [
                Item("move", f"{s:g} mm per click", lambda s=s, ax=ax: (self.back(), self.push(JogScreen(self, ax, s)))) for s in ((10, 1, 0.1) if ax != "Z" else (1, 0.1))]), sub=True)
            for ax in "XYZ"])

    def open_filament(self):
        p = self.api.printer
        warn = lambda what, fn: self.confirm(what, f"{what}: the nozzle must be hot (at least 180 °C). Uses filament.", what, fn)
        t = lambda: (self.temps() or [0])[0]
        self.menu("Filament", lambda: [
            Item("back", "Back", self.back),
            Item("nozzle", "Nozzle now", value=f"{t():.0f}°", readonly=True),
            Item("extrude", "Load", lambda: warn("Load", lambda: self.run("Load", lambda: p("load", timeout=200), then=lambda r: self.ask_loaded(), busy="Loading filament"))),
            Item("retract", "Unload", lambda: warn("Unload", lambda: self.run("Unload", lambda: p("unload", timeout=140), busy="Unloading filament"))),
            Item("extrude", "Extrude 10 mm", lambda: warn("Extrude", lambda: self.run("Extrude", lambda: p("extrude", length=10, timeout=140)))),
            Item("retract", "Retract 10 mm", lambda: warn("Retract", lambda: self.run("Retract", lambda: p("extrude", length=-10, timeout=140))))])

    def ask_loaded(self):
        """After loading: which material is it (the print check and slicing defaults use it)."""
        def pick(fam):
            try:
                self.api.set_filament(fam)
                self.toast(f"{fam} recorded as loaded", T.GOOD)
            except Exception as e:
                self.toast(str(e), T.BAD)
            self.back()
        self.menu("What did you load?", lambda: [Item("filament", "PLA", lambda: pick("PLA")), Item("filament", "PETG", lambda: pick("PETG")),
                                                Item("back", "Don't change", self.back)])

    def open_control(self):
        p = self.api.printer
        self.menu("Control", [
            Item("back", "Back", self.back),
            Item("display", "Display", self.open_display, sub=True),
            Item("motion", "Motion", self.open_motion, sub=True),
            Item("temp", "Temperature", self.open_temperature, sub=True),
            Item("crosshair", "Calibration", self.open_calibration, sub=True),
            Item("store", "Store settings", lambda: self.confirm("Store settings", "Save the printer's current settings to its EEPROM (M500)?", "Store",
                                                                  lambda: self.run("Store", lambda: p("store")), danger=True), enabled=self.idle, danger=True),
            Item("restore", "Restore settings", lambda: self.confirm("Restore settings", "Reload the settings saved in the printer's EEPROM (M501)?", "Restore",
                                                                      lambda: self.run("Restore", lambda: p("restore"))), enabled=self.idle),
            Item("info", "Info", self.open_info, sub=True)])

    def open_display(self):
        self.menu("Display", lambda: [
            Item("back", "Back", self.back),
            Item("image", "Wallpaper", self.open_wallpapers, value=self.cfg["wallpaper"].replace("-", " ").title(), sub=True),
            Item("sun", "Brightness", lambda: self.push(ValueScreen(self, "Brightness", "sun", self.cfg["brightness"], 10, 100, 5, "%", self.set_brightness)), value=f"{self.cfg['brightness']}%"),
            Item("timer", "Sleep after", lambda: self.push(ValueScreen(self, "Sleep after", "timer", self.cfg["sleep_s"] // 60, 1, 60, 1, "min", lambda v: self.save_cfg(sleep_s=int(v) * 60))),
                 value=f"{self.cfg['sleep_s'] // 60} min"),
            Item("clock", "Clock", lambda: self.save_cfg(clock24=not self.cfg.get("clock24", True)), value="24 h" if self.cfg.get("clock24", True) else "12 h")])

    def open_wallpapers(self):
        names = list(self.wallpapers)
        ls = ListScreen(self, "Wallpaper", lambda: [Item("back", "Back", self.back)] + [
            Item("image", n.replace("-", " ").title(), lambda n=n: (self.save_cfg(wallpaper=n), self.back()), value="✓" if n == self.cfg["wallpaper"] else "") for n in names])
        self.push(ls)

    def set_brightness(self, v):
        self.save_cfg(brightness=int(v))
        if not self.dimmed:
            self.c.brightness(int(v))      # apply it now, not only at the next wake-up

    def save_cfg(self, **kw):
        self.cfg.update(kw)
        if "wallpaper" in kw:
            self.set_wallpaper(kw["wallpaper"])
        try:
            self.api.save_display_config({k: self.cfg[k] for k in ("wallpaper", "brightness", "sleep_s", "clock24")})
        except Exception:
            pass

    def open_motion(self):
        box = {"s": None}

        def load():
            try:
                box["s"] = self.api.printer("settings").get("settings") or {}
            except Exception as e:
                box["s"] = {"_err": str(e)}
        threading.Thread(target=load, daemon=True).start()

        def items():
            s = box["s"]
            out = [Item("back", "Back", self.back)]
            if s is None:
                return out + [Item("spinner", "Reading the printer…", readonly=True)]
            if "_err" in s:
                return out + [Item("alert", ellipsize(s["_err"], 24), readonly=True)]
            g = lambda k, a: s.get(k, {}).get(a)
            rows = [("motion", "Max speed X/Y", f"{g('M203', 'X') or '–'}/{g('M203', 'Y') or '–'}"), ("motion", "Max speed Z", str(g("M203", "Z") or "–")),
                    ("gauge", "Accel print", str(g("M204", "P") or "–")), ("gauge", "Accel travel", str(g("M204", "T") or "–")),
                    ("crosshair", "Steps X/Y", f"{g('M92', 'X') or '–'}/{g('M92', 'Y') or '–'}"), ("crosshair", "Steps Z / E", f"{g('M92', 'Z') or '–'}/{g('M92', 'E') or '–'}")]
            return out + [Item(i, l, value=v, readonly=True) for i, l, v in rows] + [Item("info", "Edit on the web UI (Device)", readonly=True)]
        self.menu("Motion", items)

    def open_temperature(self):
        p = self.api.printer
        self.menu("Temperature", [
            Item("back", "Back", self.back),
            Item("heat", "PID tune hotend", lambda: self.confirm("PID tune", "Heat the hotend to 200 °C for several minutes and save new PID values?", "Tune",
                                                                  lambda: self.run("PID hotend", lambda: p("pid", heater="hotend", temp=200, timeout=900), busy="PID tuning hotend"), danger=True),
                 enabled=self.idle, danger=True),
            Item("bed", "PID tune bed", lambda: self.confirm("PID tune", "Heat the bed to 60 °C for several minutes and save new PID values?", "Tune",
                                                              lambda: self.run("PID bed", lambda: p("pid", heater="bed", temp=60, timeout=900), busy="PID tuning bed"), danger=True),
                 enabled=self.idle, danger=True)])

    def open_calibration(self):
        box = {"c": None}

        def load():
            try:
                box["c"] = self.api.calibrations()
            except Exception as e:
                box["c"] = {"_err": str(e)}
        threading.Thread(target=load, daemon=True).start()

        def items():
            cs = box["c"]
            out = [Item("back", "Back", self.back)]
            if cs is None:
                return out + [Item("spinner", "Loading…", readonly=True)]
            if "_err" in cs:
                return out + [Item("alert", ellipsize(cs["_err"], 24), readonly=True)]
            icons = {"tower": "layers", "plate": "level", "bands": "layers"}   # towers vs. pads on a plate
            return out + [Item(icons.get(c.get("kind"), "crosshair"), c["label"], lambda k=k, c=c: self.open_calib_test(k, c),
                               sub=True, enabled=self.idle) for k, c in cs.items()]
        self.menu("Calibration", items)

    def open_calib_test(self, key, c):
        fam = ((self.state or {}).get("filament") or {}).get("family", "PLA")
        st = {"material": "pla_loop" if fam == "PLA" else "petg_loop"}

        def defaults():
            d = c.get("defaults", {}).get("PLA" if st["material"].startswith("pla") else "PETG") or [0, 0, 1]
            st.update(start=d[0], end=d[1], step=d[2])
        defaults()
        unit = c.get("unit") or ""

        def edit(k, label):
            span = abs(st["end"] - st["start"]) or abs(st[k]) or 10
            stepsz = abs(st["step"]) / 2 if k != "step" else max(0.01, abs(st["step"]) / 5)
            self.push(ValueScreen(self, label, "crosshair", st[k], -1000 if k == "step" else 0, 10000, stepsz or 1, unit, lambda v, k=k: st.__setitem__(k, v), "{:g}"))

        def generate():
            def go():
                r = self.api.calibrate(key, st["material"], st["start"], st["end"], st["step"])
                return r
            self.run("Slicing", go, then=lambda r: self.confirm("Print test", f"{c['label']}: {r['info'].get('layers', '?')} layers, {r['info'].get('estimate', '?')}. Print it now? Check the bed is clear.",
                                                              "Print", lambda: self.run("Start print", lambda: self.api.print_file(r["name"], actions=r["info"].get("actions")), then=lambda x: self.home())),
                     busy="Slicing the test")
        self.menu(c["label"], lambda: [
            Item("back", "Back", self.back),
            Item("filament", "Material", lambda: (st.update(material="petg_loop" if st["material"].startswith("pla") else "pla_loop"), defaults()),
                 value="PLA" if st["material"].startswith("pla") else "PETG"),
            Item("up", "Start", lambda: edit("start", "Start"), value=f"{st['start']:g} {unit}"),
            Item("down", "End", lambda: edit("end", "End"), value=f"{st['end']:g} {unit}"),
            Item("move", "Step", lambda: edit("step", "Step"), value=f"{st['step']:g}"),
            Item("info", "What to look for", lambda: self.push(MessageScreen(self, c["label"], c.get("look_for", ""), T.TEAL_TEXT, "info")), sub=True),
            Item("play", "Generate & print", generate, enabled=self.idle)])

    def open_info(self):
        st = self.state or {}
        hours = (st.get("book") or {}).get("hours")
        ip = self.api.address()
        self.menu("Info", [
            Item("back", "Back", self.back),
            Item("link", "Web UI", value=ip, readonly=True),
            Item("printer", "Printer", value="V3 SE · Marlin", readonly=True),
            Item("display", "Display", value="TJC fw 68", readonly=True),
            Item("timer", "Printed", value=fmt_dur((hours or 0) * 3600), readonly=True),
            Item("filament", "Filament", value=(st.get("filament") or {}).get("family", "?"), readonly=True),
            Item("chip", "Pi", value=self.api.pi_info(), readonly=True)])

    def open_level(self):
        p = self.api.printer
        self.menu("Level", [
            Item("back", "Back", self.back),
            Item("mesh", "Bed mesh", self.open_mesh, sub=True, enabled=self.idle),
            Item("level", "Auto level", lambda: self.confirm("Auto level", "Probe the bed (several minutes) and replace the stored mesh? Bed must be clear.", "Level",
                                                              lambda: self.run("Auto level", lambda: p("level", timeout=900), then=lambda r: self.open_mesh(), busy="Levelling"), danger=True),
                 enabled=self.idle, danger=True),
            Item("zoffset", "Z offset", lambda: self.push(ValueScreen(self, "Z offset", "zoffset", 0.0, -0.5, 0.5, 0.01, "mm (+ = higher)",
                                                                       lambda v: p("zoffset", delta=v), "{:+.2f}")), enabled=self.idle)])

    def open_mesh(self):
        self.mesh = None
        self.push(MeshScreen(self))

        def load():
            try:
                self.mesh = self.api.printer("mesh", timeout=30)
            except Exception as e:
                self.toast(str(e), T.BAD)
        threading.Thread(target=load, daemon=True).start()

    # ---- input and drawing ----
    def on_turn(self, d):
        if self.wake():
            return
        with self.lock:
            self.screen.turn(d)

    def on_press(self):
        if self.wake():
            return
        with self.lock:
            self.screen.press()

    def on_long_press(self):
        if self.wake():
            return
        with self.lock:
            self.screen.long_press()

    def wake(self):
        self.last_input = time.time()
        if self.dimmed:
            self.dimmed = False
            self.c.brightness(self.cfg["brightness"])
            return True
        return False

    def el(self, key, sig, draw, force=False):
        """Draw only when sig changed. Returns True if it drew. Boxes are split into the box (drawn once) and its
        values (text over the box's own glass, no wipe), so changing numbers don't blink; force: the box was just
        repainted, so its values must be drawn again."""
        if not force and key in self.cache and self.cache[key] == sig:
            return False
        self.cache[key] = sig
        draw()
        return True

    def draw(self, full=False):
        with self.lock:
            if full or not self.cache:
                self.cache = {"__bg": 1}
                self.c.background()
            self.screen.draw(self.c)
        self.c.flush()

    def tick(self):
        if time.time() - self.state_t > 2 and not getattr(self, "_refreshing", False):
            self._refreshing = True

            def r():
                try:
                    self.refresh()
                finally:
                    self._refreshing = False
            threading.Thread(target=r, daemon=True).start()
        if self.printing():
            self.wake()                            # stays on for the whole print; sleep_s counts from the end
        elif not self.dimmed and time.time() - self.last_input > self.cfg.get("sleep_s", 300):
            self.dimmed = True                     # asleep: backlight off (dim=0); the knob, a message or a print wakes it
            self.c.brightness(0)
        self.draw()
