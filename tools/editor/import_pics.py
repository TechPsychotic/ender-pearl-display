"""Import pictures into the open TJC project in order (one at a time, so ids follow the manifest).
    python3 import_pics.py <first manifest index> [last]"""
import json, subprocess, sys, time
import os
import tjcui
ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "design", "assets")
man = json.load(open(os.path.join(ASSETS, "manifest.json")))
first = int(sys.argv[1]); last = int(sys.argv[2]) if len(sys.argv) > 2 else len(man["pictures"]) - 1


def wid(w, h):
    for l in subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True).stdout.splitlines():
        p = l.split()
        if int(p[4]) == w and int(p[5]) == h:
            return p[0]


def wait_for(w, h, t=12):
    for _ in range(int(t / 0.5)):
        i = wid(w, h)
        if i:
            return i
        time.sleep(0.5)
    raise RuntimeError(f"no {w}x{h} window")


for k in range(first, last + 1):
    f = man["pictures"][k]
    tjcui.WIN = None
    tjcui.click(17, 853, wait=0.8)
    tjcui.WIN = wait_for(660, 488)
    tjcui.click(378, 445, wait=0.3); tjcui.key("ctrl+a", wait=0.2)
    tjcui.text("Z:" + os.path.join(ASSETS, f).replace("/", "\\"), wait=0.2)   # the Wine drive Z: is /
    tjcui.key("enter", wait=0.8)
    tjcui.WIN = wait_for(481, 184)
    tjcui.click(433, 159, wait=0.6)
    print(f"{k:2d} {f}", flush=True)
