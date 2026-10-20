"""Generate the glass UI's fonts in the TJC editor's font tool, in theme.FONT_ORDER (= TJC font ids 0..6), and add each
to the open project. Uses the controls by handle (winside children/select) and Wine input for typing and clicks.
    python3 gen_fonts.py [first_role_index]"""
import json
import os
import subprocess
import sys
import time

import tjcui

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))   # tools/editor -> repo root
sys.path.insert(0, os.path.join(REPO, "design"))
from glass import theme as T  # noqa: E402

ICONS = json.load(open(os.path.join(REPO, "design", "glass", "icons.json")))["codepoints"]
FACE = {"Inter-Regular": "Inter", "Inter-Medium": "Inter Medium", "Inter-SemiBold": "Inter SemiBold", "epicons": "EPicons"}
TOOL = "字库制作工具"


def wid(w, h):
    for l in subprocess.run(["wmctrl", "-lG"], capture_output=True, text=True).stdout.splitlines():
        p = l.split()
        if int(p[4]) == w and int(p[5]) == h:
            return p[0]


def wait_for(w, h, t=90):
    for _ in range(int(t / 0.5)):
        i = wid(w, h)
        if i:
            return i
        time.sleep(0.5)
    raise RuntimeError(f"no {w}x{h} window")


def controls():
    c = {}
    for line in tjcui.wine("children", TOOL).splitlines():
        h, cls, x, y, w, hh, text = (line.split("\t") + [""])[:7]
        x, y, w, hh = int(x), int(y), int(w), int(hh)
        c.setdefault(cls, []).append({"h": h, "x": x, "y": y, "w": w, "hh": hh, "text": text})
    combos = sorted(c["WindowsForms10.COMBOBOX.app.0.33c0d9d"], key=lambda r: (r["y"], r["x"]))
    edits = c["WindowsForms10.EDIT.app.0.33c0d9d"]
    return {"height": combos[0], "encoding": combos[1], "face": combos[2], "range": combos[3],
            "height_edit": next(r for r in c["Edit"]),
            "name": next(r for r in edits if r["w"] == 110), "chars": max(edits, key=lambda r: r["w"] * r["hh"]),
            "gen": next(r for r in c["WindowsForms10.Window.8.app.0.33c0d9d"] if r["text"] == "生成字库")}


def click_abs(r, wait=0.4):
    tjcui.wine("click", r["x"] + r["w"] // 2, r["y"] + r["hh"] // 2)
    time.sleep(wait)


def open_tool():
    if any(w["title"] == TOOL for w in tjcui.windows()):
        return
    tjcui.WIN = None
    tjcui.click(56, 8, wait=0.6)        # 工具 menu
    tjcui.click(95, 33, wait=2.0)       # 字库制作


def gen(idx, role):
    h, face, chars = T.FONTS[role]
    if chars is None:
        chars = "".join(chr(v) for v in ICONS.values())
    name = f"f{idx}_{role}{h}"
    open_tool()
    c = controls()
    click_abs(c["height_edit"]); tjcui.key("ctrl+a", wait=0.2); tjcui.text(str(h), wait=0.2); tjcui.key("tab", wait=0.4)
    tjcui.wine("select", c["face"]["h"], FACE[face]); time.sleep(0.6)
    tjcui.wine("select", c["encoding"]["h"], "utf-8"); time.sleep(0.3)
    tjcui.wine("select", c["range"]["h"], "指定字符"); time.sleep(0.8)
    c = controls()                       # the dialog grows when "specified characters" is chosen
    click_abs(c["chars"]); tjcui.key("ctrl+a", wait=0.2); tjcui.key("del", wait=0.2); tjcui.text(chars, wait=0.5)
    click_abs(c["name"]); tjcui.key("ctrl+a", wait=0.2); tjcui.text(name, wait=0.3)
    click_abs(c["gen"], wait=1.0)
    tjcui.WIN = wait_for(660, 488)       # save dialog
    tjcui.click(378, 445, wait=0.3); tjcui.key("ctrl+a", wait=0.2)
    tjcui.text("Z:" + os.path.join(REPO, "fonts", name + ".zi").replace("/", "\\"), wait=0.2)   # the Wine drive Z: is /
    tjcui.key("enter", wait=1.0)
    tjcui.WIN = wait_for(481, 184, 180)  # "font generated, size ..."
    tjcui.click(433, 159, wait=1.0)
    tjcui.WIN = wait_for(481, 184)       # "add it to the project now?"
    tjcui.click(358, 159, wait=1.0)      # 是
    tjcui.WIN = None
    size = os.path.getsize(os.path.join(REPO, "fonts", name + ".zi"))
    print(f"font {idx}: {name}  ({FACE[face]}, h {h}, {len(chars)} chars, {size} bytes)", flush=True)


if __name__ == "__main__":
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    for i, role in enumerate(T.FONT_ORDER):
        if i >= first:
            gen(i, role)
