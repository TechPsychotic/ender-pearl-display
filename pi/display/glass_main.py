"""Ender Pearl on the printer display (our TJC firmware "glass", DISPLAY_RE.md plan C2).

    python3 display/glass_main.py          # normally the ender-loop-display user service

Connects on UART3, switches the link to 921600 baud with command replies on (bkcmd=3, used for flow control), stops
the display's own boot loop (tm0), plays the rest of the boot sequence, then runs the glass UI (display/glass/app.py)
with the knob (GPIO19 A, GPIO26 B, GPIO13 ENTER; a press held 0.8 s = back)."""
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import serial  # noqa: E402

import gpio  # noqa: E402
import link  # noqa: E402
from glass import app as A  # noqa: E402
from glass.canvas import TjcCanvas  # noqa: E402

KNOB_A, KNOB_B, KNOB_ENTER = 19, 26, 13
FRAME = os.path.join(ROOT, "out", "display_frame.json")
CONFIG = os.path.join(ROOT, "out", "display_config.json")   # the settings the server saves (ui/display_api.py)   # what the screen shows, for the web UI's live preview
LONG_PRESS = 0.8
INPUT_PORT = 47321     # remote knob (POST /api/display/input -> a datagram on 127.0.0.1; tools/controller)
KNOB_DIR = 1           # knob direction (1 = as decoded: clockwise moves up a list; the user prefers it; -1 flips it)
END = b"\xff\xff\xff"
MANIFEST = json.load(open(os.path.join(HERE, "glass", "manifest.json")))


class Api:
    """The web server's API (http://127.0.0.1:8080, token from ui/token.txt)."""

    def __init__(self, base="http://127.0.0.1:8080"):
        self.base = base
        with open(os.path.join(ROOT, "ui", "token.txt")) as f:
            self.token = f.read().strip()

    def call(self, method, path, body=None, timeout=8):
        req = urllib.request.Request(self.base + path, method=method, headers={"X-Token": self.token, "Content-Type": "application/json"},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error")
            except ValueError:
                msg = None
            raise RuntimeError(msg or f"HTTP {e.code}") from None

    @staticmethod
    def q(**kw):
        return "?" + urllib.parse.urlencode(kw)

    def state(self):
        return self.call("GET", "/api/state", timeout=5)

    def files(self):
        return self.call("GET", "/api/display/files")["files"]

    def plan(self, name):
        return self.call("GET", "/api/plan" + self.q(name=name), timeout=60)

    def preview(self, name, n, w, h):
        return [tuple(p) for p in self.call("GET", "/api/display/preview" + self.q(name=name, n=n, w=w, h=h), timeout=60)["paths"]]

    def model_preview(self, name, w, h):
        return [tuple(p) for p in self.call("GET", "/api/display/model" + self.q(name=name, w=w, h=h), timeout=60)["paths"]]

    def objects_preview(self, name, w, h):
        return self.call("GET", "/api/display/objects" + self.q(name=name, w=w, h=h), timeout=60)

    def printer(self, action, timeout=30, **kw):
        return self.call("POST", "/api/printer", {"action": action, **kw}, timeout=timeout)

    def cmd(self, c):
        return self.call("POST", "/api/cmd", {"cmd": c})

    def stop(self):
        return self.call("POST", "/api/stop", {})

    def print_file(self, name, actions=None):
        body = {"name": name, "bed_clear": True}
        if actions:
            body["actions"] = actions
        return self.call("POST", "/api/print", body, timeout=60)

    def sd_list(self):
        return self.printer("sd_list", timeout=90).get("files") or []

    def queue(self):
        return self.call("GET", "/api/queue")

    def queue_op(self, op, **kw):
        return self.call("POST", "/api/queue", {"op": op, **kw}, timeout=60)

    def calibrations(self):
        s = self.call("GET", "/api/settings", timeout=20)
        units = {k: v.get("unit") for k, v in (s.get("actions") or {}).items()}
        cs = s.get("calibrations") or {}
        for c in cs.values():
            c.setdefault("unit", units.get(c.get("type")) or "")
        return cs

    def calibrate(self, test, material, start, end, step):
        return self.call("POST", "/api/calibrate", {"test": test, "material": material, "start": start, "end": end, "step": step}, timeout=600)

    def set_filament(self, family):
        return self.call("POST", "/api/filament", {"family": family})

    def display_config(self):
        return self.call("GET", "/api/display/config", timeout=4)

    def save_display_config(self, cfg):
        return self.call("POST", "/api/display/config", cfg)

    def address(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("10.255.255.255", 1)); ip = s.getsockname()[0]; s.close()
            return ip
        except OSError:
            return "no network"

    def pi_info(self):
        try:
            t = int(open("/sys/class/thermal/thermal_zone0/temp").read()) / 1000
            up = float(open("/proc/uptime").read().split()[0])
            d, h = divmod(int(up // 3600), 24)
            return f"{t:.0f}°C · up {d}d {h}h" if d else f"{t:.0f}°C · up {h}h"
        except OSError:
            return "?"


def connect():
    """Open UART3 and get the display to 921600 baud with replies on. Returns the open port."""
    port = link.find_port()
    if not port:
        raise RuntimeError("no UART3 (dtoverlay=uart3)")
    for baud in (921600, 115200):          # 921600 if we set it earlier and the display was not power-cycled
        s = serial.Serial(port, baud, timeout=0.3)
        s.write(END + b"get dim" + END)
        time.sleep(0.15)
        r = s.read(32)
        if b"\x71" in r:
            if baud != 921600:
                s.write(b"baud=921600" + END); time.sleep(0.15); s.close()
                s = serial.Serial(port, 921600, timeout=0.3)
            s.reset_input_buffer()
            s.write(b"bkcmd=3" + END); time.sleep(0.05); s.reset_input_buffer()
            return s
        s.close()
    raise RuntimeError("display not answering (is our glass firmware on it?)")


def frame_writer(canvas, app):
    """Every ~0.7 s, if the screen changed: the drawing commands since the last full redraw -> out/display_frame.json.
    A long recording (many partial updates) is reset by asking the app for a full redraw."""
    import threading

    def run():
        last = -1
        while True:
            time.sleep(0.7)
            if canvas.record_v == last:
                continue
            last = canvas.record_v
            if len(canvas.record) > 6000:
                app.cache = {}
                continue
            data = {"v": last, "t": time.time(), "pics": MANIFEST["pictures"], "fonts": MANIFEST["fonts"],
                    "wallpaper": app.cfg.get("wallpaper"), "dimmed": app.dimmed, "cmds": list(canvas.record)}
            tmp = FRAME + ".tmp"
            try:
                with open(tmp, "w") as f:
                    json.dump(data, f)
                os.replace(tmp, FRAME)
            except OSError:
                pass
    threading.Thread(target=run, daemon=True).start()


def remote_input():
    """A localhost UDP socket for knob input from the web API (desktop controller). None if the port is taken."""
    try:
        rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx.bind(("127.0.0.1", INPUT_PORT))
        rx.setblocking(False)
        return rx
    except OSError as e:
        print("display: no remote input:", e, flush=True)
        return None


def remote_events(rx):
    out = []
    while rx:
        try:
            data = rx.recv(256)
        except (BlockingIOError, OSError):
            break
        try:
            m = json.loads(data)
        except ValueError:
            continue
        if isinstance(m, dict):
            out.append(m)
    return out


def saved_config(api):
    """The display settings (wallpaper, brightness, ...): from the server, or straight from its file while the server is
    still starting (both start at boot), so the screen comes back the way it was."""
    for _ in range(5):
        try:
            return api.display_config()
        except Exception:
            time.sleep(1)
    try:
        with open(CONFIG) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def main():
    while True:
        try:
            ser = connect()
            break
        except Exception as e:
            print("display:", e, flush=True)
            time.sleep(5)
    print("display connected at 921600", flush=True)
    walls = {n: w["pics"] for n, w in MANIFEST["wallpapers"].items()}
    canvas = TjcCanvas(ser, next(iter(walls.values())), MANIFEST["fonts"])
    api = Api()
    cfg = saved_config(api)
    app = A.App(api, canvas, walls, {k: cfg[k] for k in ("wallpaper", "brightness", "sleep_s", "clock24") if k in cfg})
    canvas._send("tm0.en=0")              # stop the display's own boot loop
    canvas.brightness(app.cfg["brightness"])
    boot = MANIFEST.get("boot")
    if boot:
        done = []
        splash = A.SplashScreen(app, boot, lambda: done.append(1))
        app.stack.append(splash)
        while not done:
            splash.draw(canvas); canvas.flush(); time.sleep(boot.get("dt", 0.06) / 2)
        app.stack.pop()
        time.sleep(0.6)
    app.refresh()
    app.draw(full=True)
    frame_writer(canvas, app)
    rx = remote_input()
    q = gpio.Quadrature()
    with gpio.Lines([KNOB_A, KNOB_B, KNOB_ENTER], pull="up", debounce_us=1000) as L:
        v = L.values(); q.feed(v[KNOB_A], v[KNOB_B])
        pressed_at, long_fired = None, False
        while True:
            if L.events(0.05):
                v = L.values()
                step = q.feed(v[KNOB_A], v[KNOB_B])
                if step:
                    app.on_turn(step * KNOB_DIR)
                down = v[KNOB_ENTER] == 0
                if down and pressed_at is None:
                    pressed_at, long_fired = time.time(), False
                elif not down and pressed_at is not None:
                    if not long_fired:
                        app.on_press()
                    pressed_at = None
            for m in remote_events(rx):   # the same as the knob: turn (+1 = next item / down), press, long press
                if m.get("op") == "turn":
                    app.on_turn(max(-5, min(5, int(m.get("d", 1)))))
                elif m.get("op") == "press":
                    app.on_press()
                elif m.get("op") == "long":
                    app.on_long_press()
            if pressed_at is not None and not long_fired and time.time() - pressed_at >= LONG_PRESS:
                long_fired = True
                app.on_long_press()
            app.tick()


if __name__ == "__main__":
    main()
