"""Control the TJC USART HMI editor (Wine) from Linux Python.

Input goes through Windows Python inside the same Wine prefix (winpy/winside.py: SendInput), because GNOME blocks
synthetic XTEST input to XWayland. Screenshots come from the X windows themselves (main window + popups/dialogs),
see xdrive.py. Coordinates everywhere are relative to the editor's client area, as in its screenshots.

    python3 tjcui.py shot out.png
    python3 tjcui.py click X Y [right|double]
    python3 tjcui.py text "abc"
    python3 tjcui.py key esc ctrl+s ...
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import xdrive  # noqa: E402

ENV = {**os.environ, "WINEPREFIX": os.path.expanduser("~/.wine-tjc"), "WINEDEBUG": "-all"}


def wine(*args):
    r = subprocess.run(["wine", "python.exe", "winside.py", *map(str, args)], cwd=os.path.join(HERE, "winpy"),
                       env=ENV, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        raise RuntimeError(r.stderr[-500:])
    return r.stdout


WIN = None   # title substring of the window to work in (None = main editor window)


def main_window():
    return xdrive.find(WIN)


def origin():
    return xdrive.origin(main_window())


def click(x, y, how="left", wait=0.6):
    ox, oy = origin()
    wine("click", x + ox, y + oy, how)
    time.sleep(wait)


def text(s, wait=0.3):
    wine("text", s)
    time.sleep(wait)


def key(*combos, wait=0.4):
    wine("key", *combos)
    time.sleep(wait)


def windows():
    rows = []
    for line in wine("windows").splitlines():
        h, x, y, w, hh, cls, *t = line.split("\t")
        rows.append({"hwnd": int(h), "x": int(x), "y": int(y), "w": int(w), "h": int(hh), "cls": cls, "title": t[0] if t else ""})
    return [r for r in rows if r["x"] > -1000]


def shot(path):
    return xdrive.shot(main_window(), path)


if __name__ == "__main__":
    a = sys.argv[1:]
    if "--win" in a:
        i = a.index("--win"); WIN = a[i + 1]; del a[i:i + 2]
    if a[0] == "shot":
        print(shot(a[1]))
    elif a[0] == "click":
        click(int(a[1]), int(a[2]), a[3] if len(a) > 3 else "left")
    elif a[0] == "text":
        text(a[1])
    elif a[0] == "key":
        key(*a[1:])
    elif a[0] == "windows":
        for w in windows():
            print(w)
