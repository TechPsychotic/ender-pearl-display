"""Boot animation frames for the display (Ender Pearl).
  rotate_00..17  the infinity mark turning (0..170°, loops seamlessly: the shape repeats every 180°). The display plays
                 these on its own from power-up while the Pi boots.
  morph_0..7     upright, the flat caps growing in: infinity -> Ender Pearl logo. Played by the Pi when it connects.
  text_0..3      "Ender Pearl" fading in under the logo (after the mark has risen).
Frames are small (mark 120 x 120, text 200 x 40) on the boot background, so they cost little flash.
Appends the frame picture ids to assets/manifest.json ("boot") and writes boot_preview.gif.

    python3 boot.py"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

import logo

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
BG = (8, 12, 15)
SIZE, TW, TH = 120, 200, 40
X, Y = (240 - SIZE) // 2, 100          # mark position while turning (centre of the screen)
RISE, DY = 8, 6                         # the mark moves up RISE steps of DY px
TX, TY = 20, Y - RISE * DY + SIZE + 14  # text under the risen mark


def frame(angle, morph):
    mk = logo.colour(logo.mark_mask(SIZE, angle=angle, morph=morph))
    im = Image.new("RGB", (SIZE, SIZE), BG)
    im.paste(mk, (0, 0), mk)
    return im


def text_frame(alpha):
    f = ImageFont.truetype("/usr/share/fonts/rsms-inter-fonts/Inter-SemiBold.ttf", 28)
    im = Image.new("RGB", (TW, TH), BG)
    col = tuple(int(BG[k] + (c - BG[k]) * alpha) for k, c in enumerate((225, 245, 242)))
    ImageDraw.Draw(im).text((TW / 2, TH / 2), "Ender Pearl", font=f, fill=col, anchor="mm")
    return im


def main():
    man_path = os.path.join(ASSETS, "manifest.json")
    man = json.load(open(man_path))
    man["pictures"] = [p for p in man["pictures"] if not p.startswith("boot_")]
    boot = {"rotate": [], "morph": [], "text": [], "x": X, "y": Y, "size": SIZE, "rise": RISE, "dy": DY, "tx": TX, "ty": TY,
            "bg": list(BG), "dt": 0.06}
    frames = []
    for k in range(18):
        im = frame(k * 10.0, 0.0); f = f"boot_rotate_{k:02d}.png"; im.save(os.path.join(ASSETS, f))
        boot["rotate"].append(len(man["pictures"])); man["pictures"].append(f); frames.append(("m", im))
    for k in range(8):
        im = frame(90.0, (k + 1) / 8); f = f"boot_morph_{k}.png"; im.save(os.path.join(ASSETS, f))
        boot["morph"].append(len(man["pictures"])); man["pictures"].append(f); frames.append(("m", im))
    for k in range(4):
        im = text_frame((k + 1) / 4); f = f"boot_text_{k}.png"; im.save(os.path.join(ASSETS, f))
        boot["text"].append(len(man["pictures"])); man["pictures"].append(f)
    man["boot"] = boot
    json.dump(man, open(man_path, "w"), indent=1)
    # preview GIF of the whole sequence on a 240 x 320 screen: turn twice, then morph, rise, text
    seq, scr = [], Image.new("RGB", (240, 320), BG)
    rot = [im for kind, im in frames[:18]]
    for im in rot + rot[:10]:                       # loop while "booting", stop upright (90°)
        s = scr.copy(); s.paste(im, (X, Y)); seq.append(s)
    for kind, im in frames[18:]:
        s = scr.copy(); s.paste(im, (X, Y)); seq.append(s)
    last = frames[-1][1]
    for j in range(1, RISE + 1):
        s = scr.copy(); s.paste(last, (X, Y - j * DY)); seq.append(s)
    for k in range(4):
        s = seq[-1].copy(); s.paste(text_frame((k + 1) / 4), (TX, TY)); seq.append(s)
    seq += [seq[-1]] * 12
    seq[0].save(os.path.join(HERE, "boot_preview.gif"), save_all=True, append_images=seq[1:], duration=60, loop=0)
    print(f"{len(boot['rotate'])} + {len(boot['morph'])} + {len(boot['text'])} frames; ids {boot['rotate'][0]}..{boot['text'][-1]}; preview boot_preview.gif")


if __name__ == "__main__":
    main()
