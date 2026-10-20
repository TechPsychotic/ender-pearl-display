"""Every screen of the glass UI, rendered by the real app code (glass/app.py) on the laptop canvas with fake data.
    python3 mockups.py      -> mockups/<nn>_<screen>.png, mockups/sheet.png (and sheet_wallpapers.png)"""
import json
import os
import time

from PIL import Image, ImageDraw, ImageFont

from glass import app as A
from glass.fake import FakeApi
from pilcanvas import ASSETS, PilCanvas

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "mockups")
MAN = json.load(open(os.path.join(ASSETS, "manifest.json")))
WALL = {n: w["pics"] for n, w in MAN["wallpapers"].items()}


def new_app(printing=False, wallpaper="neon-bedgrid"):
    c = PilCanvas(MAN)
    app = A.App(FakeApi(printing=printing), c, WALL, {"wallpaper": wallpaper})
    app.refresh()
    return app, c


def snap(app, c, name, out, settle=0.15, toast=None):
    time.sleep(settle)                      # background loaders (threads) finish against the fake API at once
    if toast:
        app.toast(*toast)
    app.cache = {}
    app.draw(full=True)
    p = os.path.join(OUT, f"{len(out) + 1:02d}_{name}.png")
    c.save(p)
    out.append((name, p))


def focus(app, label):
    s = app.screen
    labels = [i.label for i in s.items()]
    s.sel = labels.index(label)


def main():
    os.makedirs(OUT, exist_ok=True)
    out = []
    app, c = new_app()
    snap(app, c, "home", out)
    app.open_print(); focus(app, "From the Pi"); snap(app, c, "print", out)
    app.open_files(); time.sleep(0.2); app.screen.sel = 1; snap(app, c, "files_pi", out)
    f = FakeApi().files()[0]; app.open_file(f); time.sleep(0.2); app.screen.sel = 1; snap(app, c, "file_details", out)
    app.screen.press(); snap(app, c, "confirm_start", out)
    app.back(); app.back(); app.back()
    app.open_sd(); time.sleep(0.2); app.screen.sel = 1; snap(app, c, "files_sd", out)
    app.back(); app.open_queue(); time.sleep(0.2); app.screen.sel = 1; snap(app, c, "queue", out)
    app.home()
    app.open_prepare(); focus(app, "Move axes"); snap(app, c, "prepare", out)
    app.open_move(); focus(app, "Move X"); snap(app, c, "move_axes", out)
    app.screen.press(); app.screen.sel = 2; snap(app, c, "move_step", out)
    app.back(); app.back()
    app.push(A.JogScreen(app, "X", 1)); app.screen.pos = [117.5, 110.0, 30.0]; snap(app, c, "jog", out); app.back()
    app.open_filament(); app.screen.sel = 2; snap(app, c, "filament", out); app.back()
    app.push(A.ValueScreen(app, "Nozzle", "nozzle", 215, 0, 260, 5, "°C", lambda v: None)); snap(app, c, "value_nozzle", out); app.back()
    app.push(A.BusyScreen(app, "Homing", "Homing all axes")); snap(app, c, "busy", out); app.back()
    app.home()
    app.open_control(); focus(app, "Display"); snap(app, c, "control", out)
    app.open_display(); app.screen.sel = 1; snap(app, c, "display", out)
    app.open_wallpapers(); app.screen.sel = 2; snap(app, c, "wallpapers", out)
    app.back(); app.back()
    app.open_motion(); time.sleep(0.2); snap(app, c, "motion", out); app.back()
    app.open_temperature(); app.screen.sel = 1; snap(app, c, "temperature", out); app.back()
    app.open_info(); snap(app, c, "info", out)
    app.back(); app.open_calibration(); time.sleep(0.2); app.screen.sel = 1; snap(app, c, "calibration", out)
    app.screen.press(); app.screen.sel = 6; snap(app, c, "calib_test", out)
    app.home()
    app.open_level(); app.screen.sel = 1; snap(app, c, "level", out)
    app.open_mesh(); time.sleep(0.2); snap(app, c, "mesh", out)
    app.home()
    app.confirm("Auto level", "Probe the bed (several minutes) and replace the stored mesh? Bed must be clear.", "Level", lambda: None, danger=True)
    app.screen.sel = 1; snap(app, c, "confirm_danger", out); app.home()
    app.push(A.MessageScreen(app, "Print finished", "benchy_pla_0.2mm.gcode finished in 1h 21m. Clear the bed before the next print.", (74, 222, 128), "check2"))
    snap(app, c, "finished", out); app.home()
    snap(app, c, "home_toast", out, toast=("Preheat PLA: done", (74, 222, 128)))
    # printing
    papp, pc = new_app(printing=True)
    papp.preview(); time.sleep(0.2); papp.plan = FakeApi().plan("x")
    snap(papp, pc, "printing", out)
    papp.open_tune(); papp.screen.sel = 1; snap(papp, pc, "tune", out)
    papp.push(A.ValueScreen(papp, "Speed", "speed", 110, 50, 150, 5, "%", lambda v: None)); snap(papp, pc, "value_speed", out); papp.back()
    papp.home(); papp.screen.sel = 2; papp.screen.press(); papp.screen.sel = 1; snap(papp, pc, "stop_menu", out)
    papp.open_skip(); time.sleep(0.2); papp.screen.sel = 1; snap(papp, pc, "skip_object", out)
    papp.back(); papp.screen.sel = 2; papp.screen.press(); papp.screen.sel = 0; snap(papp, pc, "confirm_stop", out)
    sheet(out, "sheet.png", cols=6)
    # the other wallpapers: home + printing
    wout = []
    for name in WALL:
        a1, c1 = new_app(wallpaper=name); snap(a1, c1, f"home_{name}", wout)
        a2, c2 = new_app(printing=True, wallpaper=name); a2.preview(); time.sleep(0.2); a2.plan = FakeApi().plan("x"); snap(a2, c2, f"printing_{name}", wout)
    sheet(wout, "sheet_wallpapers.png", cols=6)
    print(f"{len(out)} screens + {len(wout)} wallpaper variants -> {OUT}")


def sheet(items, fname, cols=6, scale=2, gap=14):
    rows = (len(items) + cols - 1) // cols
    W, H = 240 * scale, 320 * scale
    im = Image.new("RGB", (cols * (W + gap) + gap, rows * (H + gap + 26) + gap), (22, 24, 28))
    d = ImageDraw.Draw(im)
    f = ImageFont.truetype("/usr/share/fonts/rsms-inter-fonts/Inter-Medium.ttf", 18)
    for i, (name, p) in enumerate(items):
        r, cc = divmod(i, cols)
        x, y = gap + cc * (W + gap), gap + r * (H + gap + 26)
        im.paste(Image.open(p).resize((W, H), Image.NEAREST), (x, y + 26))
        d.text((x, y + 2), f"{i + 1}. {name}", font=f, fill=(200, 210, 215))
    im.save(os.path.join(OUT, fname))


if __name__ == "__main__":
    main()
