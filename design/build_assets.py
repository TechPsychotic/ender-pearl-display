"""Wallpapers -> the three full-screen pictures each one needs on the display (240 x 320, portrait):
  <name>_bg.png     the image, cover-cropped
  <name>_glass.png  blurred, darkened, faint teal (panels)
  <name>_focus.png  lighter and more teal (the focused panel)
Sources: the procedural "grid" design plus every image in design/wallpapers (or the folders given).
Writes assets/ and assets/manifest.json (wallpaper -> picture ids in firmware order, font roles -> font ids).

    python3 build_assets.py [extra image files or folders ...]"""
import json
import os
import re
import sys

from PIL import Image, ImageOps

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import render  # noqa: E402  (glass_of, bg_grid)
from glass import theme as T  # noqa: E402

OUT = os.path.join(HERE, "assets")
WALLDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wallpapers")
IMG = re.compile(r"\.(png|jpe?g|webp|bmp)$", re.I)


def slug(path, used):
    base = re.sub(r"[^a-z0-9]+", "-", os.path.splitext(os.path.basename(path))[0].lower()).strip("-")[:16] or "wallpaper"
    name, k = base, 2
    while name in used:
        name, k = f"{base}-{k}", k + 1
    return name


def cover(path, focus_y=0.5):
    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert("RGB")
    return ImageOps.fit(im, (T.W, T.H), Image.LANCZOS, centering=(0.5, focus_y))


def readable(bg):
    """Tame very bright images a little so glass panels and text stay legible."""
    from PIL import ImageStat, ImageEnhance
    lum = sum(ImageStat.Stat(bg.convert("L")).mean) / 255
    return ImageEnhance.Brightness(bg).enhance(0.92 if lum < 0.35 else 0.75 if lum < 0.6 else 0.6)


def main(extra):
    os.makedirs(OUT, exist_ok=True)
    sources = [("neon-bedgrid", None)]
    used = {"neon-bedgrid"}
    paths = []
    for p in ([WALLDIR] if os.path.isdir(WALLDIR) else []) + extra:
        if os.path.isdir(p):
            paths += [os.path.join(p, f) for f in sorted(os.listdir(p)) if IMG.search(f)]
        elif IMG.search(p):
            paths.append(p)
    names_file = os.path.join(HERE, "wallpaper_names.json")   # friendly names for the menu (file name -> name)
    names = json.load(open(names_file)) if os.path.exists(names_file) else {}
    for p in paths:
        n = names.get(os.path.basename(p)) or slug(p, used)
        n = slug(n, used); used.add(n); sources.append((n, p))
    manifest = {"wallpapers": {}, "pictures": [], "fonts": {r: i for i, r in enumerate(T.FONT_ORDER)}}
    for name, path in sources:
        bg = render.bg_grid() if path is None else readable(cover(path))
        layers = {"bg": bg, "glass": render.glass_of(bg), "focus": render.glass_of(bg, True)}
        ids = {}
        for layer, im in layers.items():
            f = f"{name}_{layer}.png"
            im.save(os.path.join(OUT, f))
            ids[layer] = len(manifest["pictures"])
            manifest["pictures"].append(f)
        manifest["wallpapers"][name] = {"pics": ids, "source": os.path.basename(path) if path else "procedural grid"}
    with open(os.path.join(OUT, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    print(f"{len(sources)} wallpapers, {len(manifest['pictures'])} pictures -> {OUT}")
    for n, w in manifest["wallpapers"].items():
        print(f"  {n:18s} pics {w['pics']}  ({w['source']})")


if __name__ == "__main__":
    main(sys.argv[1:])
