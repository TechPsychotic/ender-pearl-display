"""Ender Loop on the printer's own display (TJC3224 on the Pi's UART3, knob on GPIO19/26/13; DISPLAY_RE.md).

Everything goes through the web server's API (http://127.0.0.1:8080, token from ui/token.txt), never the printer's
serial port: the screen and the browser show the same state, and every check (bed clear, filament family, idle-only
moves, live-override limits) stays in one place.

    python3 display/ui.py            # normally run by the ender-loop-display user service
    python3 display/ui.py --demo     # fake printer data, no server needed (display + knob only)

Knob: turn = move the highlight / change a value, press = select / confirm. The backlight dims after 5 minutes;
the first touch only wakes it."""
import argparse
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocol as D  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 240, 320
F, FH = D.FONTS["8x16"], 20             # list font and row height
COLS = W // 8                            # 30 characters per row
BODY_Y, ROWS = 30, 13                    # first body row, rows that fit above the footer
FOOT_Y = 300
C_BG, C_HEAD, C_TEXT, C_DIM = D.rgb565(16, 18, 22), D.rgb565(40, 44, 52), D.WHITE, D.rgb565(140, 148, 160)
C_ACC, C_WARN, C_BAD = D.rgb565(34, 197, 94), D.rgb565(245, 180, 40), D.rgb565(239, 68, 68)
KNOB_A, KNOB_B, KNOB_ENTER = 19, 26, 13
DIM_AFTER, BRIGHT, DIM = 300, 48, 6
PREHEAT = [("Preheat PLA", "pla_loop"), ("Preheat PETG", "petg_loop")]


# ---------------------------------------------------------------- server API
class Api:
    def __init__(self, base="http://127.0.0.1:8080", token_file=os.path.join(ROOT, "ui", "token.txt")):
        self.base = base
        with open(token_file) as f:
            self.token = f.read().strip()

    def call(self, method, path, body=None, timeout=5):
        req = urllib.request.Request(self.base + path, method=method, headers={"X-Token": self.token, "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:   # the server answers errors as {"error": "..."}
            try:
                msg = json.loads(e.read()).get("error")
            except ValueError:
                msg = None
            raise RuntimeError(msg or f"HTTP {e.code}") from None

    def state(self):
        return self.call("GET", "/api/state", timeout=4)

    def files(self):
        return [f["name"] for f in self.call("GET", "/api/files")["files"] if f["kind"] == "gcode"]

    def printer(self, action, timeout=30, **kw):
        return self.call("POST", "/api/printer", {"action": action, **kw}, timeout=timeout)

    def cmd(self, c):
        return self.call("POST", "/api/cmd", {"cmd": c})

    def print_file(self, name):
        return self.call("POST", "/api/print", {"name": name, "bed_clear": True}, timeout=60)

    def stop(self):
        return self.call("POST", "/api/stop", {})


class FakeApi:
    """--demo and the tests: a printer that prints slowly."""
    def __init__(self):
        self.calls, self.t0, self.printing = [], time.time(), False

    def state(self):
        if not self.printing:
            return {"printing": False, "idle_temps": [24.0, 0, 23.5, 0], "filament": {"family": "PLA"}, "queue": {}, "book": {"hours": 1.2}}
        k = min(1.0, (time.time() - self.t0) / 600)
        return {"printing": True, "job": "demo_cube.gcode", "filament": {"family": "PLA"}, "queue": {}, "book": {"hours": 1.2},
                "status": {"state": "printing", "layer": int(99 * k), "layers": 100, "temps": [195, 195, 55, 55], "sent": int(1e4 * k),
                           "total": 10000, "remaining": 600 * (1 - k), "finish_at": self.t0 + 600, "updated": time.time(), "overrides": {}}}

    def files(self):
        return ["demo_cube.gcode", "clearance_test.gcode"]

    def printer(self, action, timeout=30, **kw):
        self.calls.append(("printer", action, kw)); return {"ok": True}

    def cmd(self, c):
        self.calls.append(("cmd", c)); return {"ok": True}

    def print_file(self, name):
        self.calls.append(("print", name)); self.printing, self.t0 = True, time.time(); return {"ok": True}

    def stop(self):
        self.calls.append(("stop",)); self.printing = False; return {"ok": True}


# ---------------------------------------------------------------- helpers
def fmt_dur(s):
    s = int(max(0, s or 0)); h, m = divmod(s // 60, 60)
    return f"{h}h {m:02d}m" if h else f"{m} min"


def temps_of(st):
    if not st:
        return None
    if st.get("printing") and st.get("status"):
        return st["status"].get("temps")
    return st.get("idle_temps")


def wrap(text, width=COLS):
    out, line = [], ""
    for w in str(text).split():
        if len(line) + len(w) + (1 if line else 0) > width:
            out.append(line); line = w[:width]
        else:
            line = f"{line} {w}" if line else w[:width]
    return out + ([line] if line else [])


def ip_address():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]; s.close(); return ip
    except OSError:
        return "no network"


# ---------------------------------------------------------------- screens
class Item:
    def __init__(self, label, action=None, value=None):
        self.label, self.action, self.value = label, action, value   # value: callable → text shown on the right


class Screen:
    title = ""

    def __init__(self, app):
        self.app = app

    def lines(self):          # [(text, fg, bg)] for the body rows
        return []

    def turn(self, d):
        pass

    def press(self):
        pass


class Menu(Screen):
    """A list: the highlight moves with the knob; press runs the item's action. Item 0 is usually "< Back"."""
    def __init__(self, app, title, items_fn, header_fn=None):
        super().__init__(app)
        self.title, self.items_fn, self.header_fn, self.sel, self.top = title, items_fn, header_fn, 0, 0

    def items(self):
        return self.items_fn()

    def lines(self):
        head = self.header_fn() if self.header_fn else []
        items = self.items()
        self.sel = max(0, min(self.sel, len(items) - 1))
        room = ROWS - len(head)
        if self.sel < self.top:
            self.top = self.sel
        if self.sel >= self.top + room:
            self.top = self.sel - room + 1
        out = list(head)
        for i, it in enumerate(items[self.top:self.top + room], self.top):
            v = it.value() if it.value else ""
            txt = (it.label + " " * COLS)[:COLS - len(v) - 1] + " " + v if v else it.label
            out.append((txt, C_BG, C_ACC) if i == self.sel else (txt, C_TEXT, C_BG))
        return out

    def turn(self, d):
        self.sel = max(0, min(len(self.items()) - 1, self.sel + d))

    def press(self):
        items = self.items()
        if items and items[self.sel].action:
            items[self.sel].action()


class Value(Screen):
    """Edit a number: turn changes it, press sends it and goes back."""
    def __init__(self, app, title, value, lo, hi, step, unit, commit, fmt="{:.0f}"):
        super().__init__(app)
        self.title, self.v, self.lo, self.hi, self.step, self.unit, self.commit, self.fmt = title, value, lo, hi, step, unit, commit, fmt

    def lines(self):
        return [("", C_TEXT, C_BG), (f"  {self.fmt.format(self.v)} {self.unit}", C_ACC, C_BG), ("", C_TEXT, C_BG),
                (f"range {self.fmt.format(self.lo)} - {self.fmt.format(self.hi)} {self.unit}", C_DIM, C_BG),
                ("turn to change,", C_DIM, C_BG), ("press to set", C_DIM, C_BG)]

    def turn(self, d):
        self.v = round(max(self.lo, min(self.hi, self.v + d * self.step)), 4)

    def press(self):
        v = self.v
        self.app.back()
        self.app.run(f"{self.title}: {self.fmt.format(v)} {self.unit}", lambda: self.commit(v))


class Jog(Screen):
    """Move one axis: each detent moves `step` mm; moves are sent together at most every 0.25 s."""
    def __init__(self, app, axis, step):
        super().__init__(app)
        self.title, self.axis, self.step, self.pending, self.moved, self.lock = f"Move {axis} by {step:g} mm", axis, step, 0.0, 0.0, threading.Lock()
        threading.Thread(target=self._sender, daemon=True).start()

    def _sender(self):
        while self.app.screen is self or self.pending:
            time.sleep(0.25)
            with self.lock:
                d, self.pending = round(self.pending, 3), 0.0
            if d:
                try:
                    self.app.api.printer("jog", axis=self.axis, dist=max(-10 if self.axis == "Z" else -100, min(10 if self.axis == "Z" else 100, d)))
                    self.moved += d
                except Exception as e:   # e.g. "printing" or the printer is off: show and stop sending
                    self.app.toast(str(e), C_BAD)

    def lines(self):
        return [("", C_TEXT, C_BG), (f"  {self.axis} moved {self.moved:+.1f} mm", C_ACC, C_BG), ("", C_TEXT, C_BG),
                ("turn = move, press = done", C_DIM, C_BG), ("Home first if the printer was", C_DIM, C_BG), ("just switched on.", C_DIM, C_BG)]

    def turn(self, d):
        with self.lock:
            self.pending += d * self.step

    def press(self):
        self.app.back()


class Message(Screen):
    def __init__(self, app, title, text, color=C_TEXT):
        super().__init__(app)
        self.title, self.text, self.color = title, text, color

    def lines(self):
        return [(l, self.color, C_BG) for l in wrap(self.text)[:ROWS - 1]] + [("", C_TEXT, C_BG), ("press to go back", C_DIM, C_BG)]

    def press(self):
        self.app.back()


def confirm(app, title, question, yes_label, on_yes):
    """No is selected first; Yes runs on_yes."""
    def yes():
        app.back(); on_yes()
    m = Menu(app, title, lambda: [Item("No, go back", app.back), Item(yes_label, yes)],
             lambda: [(l, C_WARN, C_BG) for l in wrap(question)] + [("", C_TEXT, C_BG)])
    app.push(m)


# ---------------------------------------------------------------- the app
class App:
    def __init__(self, api, display=None):
        self.api, self.disp = api, display
        self.state, self.state_err, self.state_t = None, None, 0
        self.stack, self.cache, self.msg = [], {}, None
        self.last_input, self.dimmed, self.busy = time.time(), False, None
        self.lock = threading.RLock()
        self.push(self.home_screen())

    # navigation
    @property
    def screen(self):
        return self.stack[-1]

    def push(self, s):
        self.stack.append(s); self.cache = {}

    def back(self):
        if len(self.stack) > 1:
            self.stack.pop(); self.cache = {}

    def home(self):
        del self.stack[1:]; self.cache = {}

    def toast(self, text, color=C_TEXT, secs=6):
        self.msg = (text, color, time.time() + secs)

    def run(self, label, fn, then=None):
        """Run an API call in the background; the footer shows progress and the result."""
        if self.busy:
            return self.toast("busy: wait for the last action", C_WARN)
        self.busy = label
        self.toast(label + "...", C_DIM, 600)

        def work():
            try:
                r = fn()
                self.toast(f"{label}: done", C_ACC)
                if then:
                    then(r)
            except Exception as e:
                self.toast("", C_BG, 0)
                with self.lock:
                    self.push(Message(self, "Not done", str(e), C_BAD))
            finally:
                self.busy = None
                self.state_t = 0   # refresh now
        threading.Thread(target=work, daemon=True).start()

    # state
    def refresh(self):
        try:
            self.state, self.state_err = self.api.state(), None
        except Exception as e:
            self.state_err = str(e) or "server not reachable"
        self.state_t = time.time()

    def printing(self):
        return bool(self.state and (self.state.get("printing") or self.state.get("sd")))

    # screens
    def status_lines(self):
        st, out = self.state, []
        if self.state_err:
            return [("Server not reachable:", C_BAD, C_BG)] + [(l, C_DIM, C_BG) for l in wrap(self.state_err)[:2]] + [("", C_TEXT, C_BG)]
        if not st:
            return [("connecting...", C_DIM, C_BG)]
        t = temps_of(st)
        if t:
            out.append((f"Nozzle {t[0]:5.1f} / {t[1]:3.0f} C", C_TEXT, C_BG))
            out.append((f"Bed    {t[2]:5.1f} / {t[3]:3.0f} C", C_TEXT, C_BG))
        else:
            out.append(("printer not connected", C_WARN, C_BG))
        s = st.get("status") or {}
        if st.get("printing"):
            name = (st.get("job") or s.get("file") or "")[:COLS]
            paused = s.get("state") == "paused"
            out.append((name, C_ACC, C_BG))
            p = (s.get("sent", 0) / s["total"]) if s.get("total") else 0
            bar = int(p * 20)
            out.append(("[" + "#" * bar + "." * (20 - bar) + f"] {p * 100:3.0f}%", C_WARN if paused else C_ACC, C_BG))
            rem = s.get("remaining")
            rem = max(0, rem - (time.time() - s.get("updated", time.time()))) if rem is not None else None
            fin = time.strftime("%H:%M", time.localtime(s["finish_at"])) if s.get("finish_at") else "-"
            out.append((f"Layer {s.get('layer', -1) + 1}/{s.get('layers', 0)}  " + ("PAUSED" if paused else f"{fmt_dur(rem)} left" if rem is not None else ""), C_TEXT, C_BG))
            out.append((f"Done at {fin}", C_DIM, C_BG))
        elif st.get("sd"):
            out.append(("Printing from SD: " + str(st["sd"].get("file") or "")[:12], C_ACC, C_BG))
        else:
            fil = (st.get("filament") or {}).get("family", "?")
            out.append((f"Idle  -  {fil} loaded", C_DIM, C_BG))
        q = st.get("queue") or {}
        if q.get("alert"):
            out.append((str(q["alert"])[:COLS], C_WARN, C_BG))
        out.append(("", C_TEXT, C_BG))
        return out

    def home_screen(self):
        def items():
            if self.printing():
                s = (self.state.get("status") or {})
                paused = s.get("state") == "paused" or (self.state.get("sd") or {}).get("paused")
                if self.state.get("sd"):
                    return [Item("Resume SD print" if paused else "Pause SD print", lambda: self.run("SD " + ("resume" if paused else "pause"), lambda: self.api.printer("sd_resume" if paused else "sd_pause"))),
                            Item("Stop SD print", lambda: confirm(self, "Stop", "Stop the SD print? It can't be resumed.", "Yes, stop", lambda: self.run("Stop", lambda: self.api.printer("sd_stop")))),
                            Item("Info", lambda: self.push(self.info_screen()))]
                return [Item("Resume" if paused else "Pause", lambda: self.run("Resume" if paused else "Pause", lambda: self.api.cmd("resume" if paused else "pause"))),
                        Item("Tune", lambda: self.push(self.tune_screen())),
                        Item("Stop print", lambda: confirm(self, "Stop print", "Stop this print? It can't be resumed.", "Yes, stop it", lambda: self.run("Stop", self.api.stop))),
                        Item("Info", lambda: self.push(self.info_screen()))]
            return [Item("Print a file", lambda: self.push(self.files_screen())), Item("Prepare", lambda: self.push(self.prepare_screen())),
                    Item("Info", lambda: self.push(self.info_screen()))]
        m = Menu(self, "Ender Loop", items, self.status_lines)
        return m

    def files_screen(self):
        files = {"list": None, "err": None}

        def load():
            try:
                files["list"] = self.api.files()[:40]
            except Exception as e:
                files["err"] = str(e)
        threading.Thread(target=load, daemon=True).start()

        def items():
            out = [Item("< Back", self.back)]
            if files["err"]:
                return out + [Item(files["err"][:COLS])]
            if files["list"] is None:
                return out + [Item("loading...")]
            if not files["list"]:
                return out + [Item("no G-code files yet")]
            return out + [Item(n[:COLS], (lambda n=n: self.start_print(n))) for n in files["list"]]
        return Menu(self, "Print a file", items)

    def start_print(self, name):
        confirm(self, "Start print", f"Print {name}? Check the bed is clear and the right filament is loaded.", "Bed is clear: print",
                lambda: self.run("Start print", lambda: self.api.print_file(name), then=lambda r: self.home()))

    def prepare_screen(self):
        def t(i):
            v = temps_of(self.state)
            return v[i] if v else 0

        def items():
            out = [Item("< Back", self.back), Item("Home all axes", lambda: self.run("Homing", lambda: self.api.printer("home", timeout=200)))]
            for ax in ("X", "Y", "Z"):
                out.append(Item(f"Move {ax}", lambda ax=ax: self.push(Menu(self, f"Move {ax}: step", lambda ax=ax: [Item("< Back", self.back)] + [
                    Item(f"{s:g} mm per click", lambda s=s, ax=ax: (self.back(), self.push(Jog(self, ax, s)))) for s in ((10, 1, 0.1) if ax != "Z" else (1, 0.1))]))))
            for label, mat in PREHEAT:
                out.append(Item(label, lambda mat=mat, label=label: self.run(label, lambda: self.api.printer("preheat", material=mat))))
            out += [Item("Cool down", lambda: self.run("Cool down", lambda: self.api.printer("cooldown"))),
                    Item("Nozzle temperature", lambda: self.push(Value(self, "Nozzle", round(t(1)), 0, 260, 5, "C", lambda v: self.api.printer("temps", nozzle=v))), lambda: f"{t(1):.0f} C"),
                    Item("Bed temperature", lambda: self.push(Value(self, "Bed", round(t(3)), 0, 100, 5, "C", lambda v: self.api.printer("temps", bed=v))), lambda: f"{t(3):.0f} C"),
                    Item("Fan", lambda: self.push(Value(self, "Fan", 0, 0, 100, 10, "%", lambda v: self.api.printer("fan", percent=v)))),
                    Item("Park the head", lambda: self.run("Park", lambda: self.api.printer("park", timeout=60))),
                    Item("Motors off", lambda: self.run("Motors off", lambda: self.api.printer("motors_off")))]
            return out
        return Menu(self, "Prepare", items)

    def tune_screen(self):
        def ov(k, d):
            return ((self.state or {}).get("status") or {}).get("overrides", {}).get(k, d)

        def tv(i):
            v = temps_of(self.state)
            return v[i] if v else 0

        def items():
            return [Item("< Back", self.back),
                    Item("Speed", lambda: self.push(Value(self, "Speed", round(ov("speed", 1) * 100), 50, 150, 5, "%", lambda v: self.api.cmd(f"speed {v / 100:g}"))), lambda: f"{ov('speed', 1) * 100:.0f}%"),
                    Item("Flow", lambda: self.push(Value(self, "Flow", round(ov("flow", 1) * 100), 80, 120, 1, "%", lambda v: self.api.cmd(f"flow {v / 100:g}"))), lambda: f"{ov('flow', 1) * 100:.0f}%"),
                    Item("Fan", lambda: self.push(Value(self, "Fan", round(ov("fan", 100)), 0, 100, 5, "%", lambda v: self.api.cmd(f"fan {v:g}")))),
                    Item("Nozzle", lambda: self.push(Value(self, "Nozzle", round(tv(1)), 0, 260, 1, "C", lambda v: self.api.cmd(f"temp {v:g}"))), lambda: f"{tv(1):.0f} C"),
                    Item("Bed", lambda: self.push(Value(self, "Bed", round(tv(3)), 0, 100, 1, "C", lambda v: self.api.cmd(f"bed {v:g}"))), lambda: f"{tv(3):.0f} C"),
                    Item("Z babystep", lambda: self.push(Value(self, "Z babystep", 0.0, -0.2, 0.2, 0.01, "mm", lambda v: self.api.cmd(f"babystep {v:g}"), "{:+.2f}")),
                         lambda: f"{ov('babystep', 0):+.2f}")]
        return Menu(self, "Tune", items)

    def info_screen(self):
        st = self.state or {}
        hours = (st.get("book") or {}).get("hours")
        lines = ["Web UI:", f"  http://{ip_address()}:8080", "Printing time logged",
                 f"  {fmt_dur(hours * 3600) if isinstance(hours, (int, float)) else '?'} (maintenance book)",
                 f"Filament: {(st.get('filament') or {}).get('family', '?')}", f"Display: {getattr(self.disp, 'port', '-')}"]
        return Menu(self, "Info", lambda: [Item("< Back", self.back)], lambda: [(l[:COLS], C_TEXT, C_BG) for l in lines] + [("", C_TEXT, C_BG)])

    # input
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

    def wake(self):
        self.last_input = time.time()
        if self.dimmed:
            self.dimmed = False
            self.send(D.backlight(BRIGHT))
            return True
        return False

    # drawing
    def send(self, *frames):
        if self.disp:
            self.disp.send(*frames)

    def frame_rows(self):
        """{y: (text, fg, bg)} for the whole screen (header, body, footer)."""
        with self.lock:
            s = self.screen
            rows = {0: ((" " + s.title)[:COLS - 6].ljust(COLS - 6) + time.strftime("%H:%M"), C_TEXT, C_HEAD)}
            body = s.lines()[:ROWS]
        for i in range(ROWS):
            rows[BODY_Y + i * FH] = body[i] if i < len(body) else ("", C_TEXT, C_BG)
        m = self.msg
        rows[FOOT_Y] = (m[0][:COLS], m[1], C_BG) if m and time.time() < m[2] else ("", C_TEXT, C_BG)
        return rows

    def draw(self, full=False):
        if full or not self.cache:
            self.send(D.clear(C_BG), D.colors(C_HEAD, C_HEAD), D.fill_rect(0, 0, W - 1, 23))
            self.cache = {}
        frames = []
        for y, (text, fg, bg) in self.frame_rows().items():
            key = (text, fg, bg)
            if self.cache.get(y) == key:
                continue
            self.cache[y] = key
            top, h = (0, 24) if y == 0 else (y - 2, FH)
            frames += [D.colors(bg, bg), D.fill_rect(0, top, W - 1, min(H - 1, top + h - 1))]
            if text.strip():
                # no background box: the font's box is taller than a row and bled into the next one; the row is filled above
                frames.append(D.text(4 if y else 0, y + (4 if y == 0 else 0), text, F, fg, bg, False))
        if frames:
            self.send(*frames)

    def tick(self):
        if time.time() - self.state_t > 2 and not getattr(self, "_refreshing", False):
            self._refreshing = True

            def r():
                try:
                    self.refresh()
                finally:
                    self._refreshing = False
            threading.Thread(target=r, daemon=True).start()
        if not self.dimmed and time.time() - self.last_input > DIM_AFTER:
            self.dimmed = True
            self.send(D.backlight(DIM))
        self.draw()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="fake printer data (no server)")
    ap.add_argument("--port")
    a = ap.parse_args()
    import gpio
    import link
    while True:   # wait for the display (it may be unplugged or still booting)
        try:
            d = link.Display(a.port)
            if d.handshake():
                break
            d.close()
        except Exception as e:
            print("display:", e, flush=True)
        time.sleep(5)
    print(f"display on {d.port}: handshake OK", flush=True)
    app = App(FakeApi() if a.demo else Api(), d)
    d.send(D.backlight(BRIGHT))
    app.refresh(); app.draw(full=True)
    q = gpio.Quadrature()
    with gpio.Lines([KNOB_A, KNOB_B, KNOB_ENTER], pull="up", debounce_us=1000) as L:
        v = L.values(); q.feed(v[KNOB_A], v[KNOB_B]); pressed = v[KNOB_ENTER] == 0
        last_full = time.time()
        while True:
            if L.events(0.1):
                v = L.values()
                step = q.feed(v[KNOB_A], v[KNOB_B])
                if step:
                    app.on_turn(step)
                p = v[KNOB_ENTER] == 0
                if p and not pressed:
                    app.on_press()
                pressed = p
            app.tick()
            if time.time() - last_full > 600:   # repaint everything now and then, in case the display reset
                app.draw(full=True); last_full = time.time()


if __name__ == "__main__":
    main()
