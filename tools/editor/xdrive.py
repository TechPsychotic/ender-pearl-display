"""Drive the TJC USART HMI editor (Wine, XWayland) from Python: screenshots + synthetic mouse/keyboard (XTEST).

    python3 xdrive.py shot [out.png]          # screenshot of the editor window
    python3 xdrive.py click X Y [right|double] # window-relative pixel coordinates (as in the screenshot)
    python3 xdrive.py type "text"
    python3 xdrive.py key Return | ctrl+s | alt+f | Escape ...
    python3 xdrive.py windows                 # list Wine windows (dialogs too)
Coordinates are relative to the chosen window (default: the main editor window; --win <title part or 0xid>)."""
import subprocess
import sys
import time

from Xlib import X, XK, display
from Xlib.ext import xtest

D = display.Display(":0")
ROOT = D.screen().root


def windows():
    out = subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True).stdout.splitlines()
    res = []
    for l in out:
        p = l.split(None, 7)
        if len(p) >= 7:
            res.append({"id": int(p[0], 16), "x": int(p[2]), "y": int(p[3]), "w": int(p[4]), "h": int(p[5]), "title": p[7] if len(p) > 7 else ""})
    return res


def find(sel=None):
    ws = windows()
    if sel and sel.startswith("0x"):
        return next(w for w in ws if w["id"] == int(sel, 16))
    cands = [w for w in ws if (sel or "USART HMI") in w["title"]]
    if not cands:
        raise LookupError(f"no window titled like {sel!r}")
    return max(cands, key=lambda w: w["w"] * w["h"]) if not sel else cands[0]


def origin(w):
    win = D.create_resource_object("window", w["id"])
    t = win.translate_coords(ROOT, 0, 0)
    return -t.x, -t.y


def visible_windows():
    """Every viewable top-level X window (incl. override-redirect popup menus), bottom to top."""
    out = []
    for win in ROOT.query_tree().children:
        try:
            a = win.get_attributes()
            if a.map_state != X.IsViewable:
                continue
            g = win.get_geometry()
            t = win.translate_coords(ROOT, 0, 0)
            out.append((win, -t.x, -t.y, g.width, g.height))
        except Exception:
            pass
    return out


def grab(win, w, h):
    img = win.get_image(0, 0, w, h, X.ZPixmap, 0xFFFFFFFF)
    return img.data


def shot(w, path):
    """The window as seen on screen: its own pixels (grabbed by id, so framed dialogs work too), with any popup menus
    or drop-down lists (override-redirect windows) that overlap it pasted on top."""
    import os, tempfile
    ox, oy = origin(w)
    me = D.create_resource_object("window", w["id"])
    g = me.get_geometry()
    layers = [(0, 0, g.width, g.height, grab(me, g.width, g.height))]
    for win, x, y, ww, hh in visible_windows():
        if win.id == w["id"] or ww < 2 or hh < 2 or x + ww <= ox or y + hh <= oy or x >= ox + g.width or y >= oy + g.height:
            continue
        try:
            if not win.get_attributes().override_redirect:
                continue
            layers.append((x - ox, y - oy, ww, hh, grab(win, ww, hh)))
        except Exception:
            continue
    tmp = tempfile.mkdtemp()
    cmd = ["magick", "-size", f"{g.width}x{g.height}", "xc:black"]
    for i, (x, y, ww, hh, data) in enumerate(layers):
        f = os.path.join(tmp, f"{i}.bgra")
        open(f, "wb").write(data)
        cmd += ["(", "-size", f"{ww}x{hh}", "-depth", "8", f"bgra:{f}", "-alpha", "off", ")", "-geometry", f"+{x}+{y}", "-composite"]
    subprocess.run(cmd + [path], check=True)
    return path


def move(x, y):
    xtest.fake_input(D, X.MotionNotify, x=x, y=y); D.sync()


def click(w, x, y, how="left"):
    ox, oy = origin(w)
    move(ox + x, oy + y); time.sleep(0.08)
    btn = 3 if how == "right" else 1
    for _ in range(2 if how == "double" else 1):
        xtest.fake_input(D, X.ButtonPress, btn); D.sync(); time.sleep(0.05)
        xtest.fake_input(D, X.ButtonRelease, btn); D.sync(); time.sleep(0.08)


KEYMAP = {"ctrl": "Control_L", "alt": "Alt_L", "shift": "Shift_L", "enter": "Return", "esc": "Escape", "tab": "Tab",
          "del": "Delete", "space": "space", "\\": "backslash", ":": "colon", ".": "period", "/": "slash", "_": "underscore",
          "-": "minus", "=": "equal", "\"": "quotedbl", ",": "comma", " ": "space", "(": "parenleft", ")": "parenright"}


def keycode(name):
    ks = XK.string_to_keysym(KEYMAP.get(name, name))
    if not ks:
        raise ValueError(f"unknown key {name!r}")
    return D.keysym_to_keycode(ks), ks


def key(combo):
    parts = combo.split("+") if len(combo) > 1 else [combo]
    codes = [keycode(p)[0] for p in parts]
    for c in codes:
        xtest.fake_input(D, X.KeyPress, c); D.sync(); time.sleep(0.02)
    for c in reversed(codes):
        xtest.fake_input(D, X.KeyRelease, c); D.sync(); time.sleep(0.02)
    time.sleep(0.05)


def type_text(s):
    for ch in s:
        code, ks = keycode(ch)
        shift = ch.isupper() or ch in '"_:()!@#$%^&*{}|<>?~+'
        if shift:
            xtest.fake_input(D, X.KeyPress, keycode("shift")[0])
        xtest.fake_input(D, X.KeyPress, code); xtest.fake_input(D, X.KeyRelease, code)
        if shift:
            xtest.fake_input(D, X.KeyRelease, keycode("shift")[0])
        D.sync(); time.sleep(0.03)


if __name__ == "__main__":
    args = sys.argv[1:]
    sel = None
    if "--win" in args:
        i = args.index("--win"); sel = args[i + 1]; del args[i:i + 2]
    cmd = args[0]
    if cmd == "windows":
        for w in windows():
            print(hex(w["id"]), w["x"], w["y"], w["w"], w["h"], w["title"])
        sys.exit()
    w = find(sel)
    if cmd == "shot":
        print(shot(w, args[1] if len(args) > 1 else "/tmp/tjc_shot.png"))
    elif cmd == "click":
        click(w, int(args[1]), int(args[2]), args[3] if len(args) > 3 else "left")
    elif cmd == "type":
        type_text(args[1])
    elif cmd == "key":
        for k in args[1:]:
            key(k)
