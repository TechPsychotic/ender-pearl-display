# Design and assets (laptop side)

Everything in `design/` runs on a normal PC with Python 3 and Pillow. `design/glass` is a link to
`pi/display/glass`, so the mockups use exactly the code that runs on the Pi.

| Script | Output |
|---|---|
| `build_assets.py [images…]` | for the procedural "neon bedgrid" and every image in `design/wallpapers/`: `assets/<name>_bg/_glass/_focus.png` (240 × 320, cover-cropped) and `assets/manifest.json` (picture ids in firmware order, font roles → font ids). Friendly names come from `wallpaper_names.json` |
| `boot.py` | boot animation frames: the logo mark rotating (played by the display itself from power-up), morphing into the Ender Pearl logo, and the name fading in (played by the Pi when it connects). `boot_preview.gif` |
| `logo.py` | the logo: a lemniscate stood on end, top and bottom cut flat and capped, teal gradient with a glow. `logo/logo_<size>.png` |
| `build_metrics.py` | glyph widths from `fonts/*.zi` → `glass/metrics.json` |
| `render.py` | early design studies: backgrounds, glass layers, mockups made only of things the display can reproduce |
| `mockups.py` | every screen rendered by the real app (`glass/app.py`) on a Pillow canvas with fake data → `mockups/*.png`, `sheet.png`, `sheet_wallpapers.png` |
| `pilcanvas.py` | the laptop canvas. It mimics the TJC canvas, including `xstr` cropping its box background from a picture |
| `MENUS.md` | the menu specification: every screen and item |

The icon font (`icons/epicons.ttf`) holds 61 Lucide icons mapped onto plain ASCII letters (`print` = "A",
`play` = "B", …; see `icons/icons.json` and `pi/display/glass/icons.json`), which keeps them easy to select in the
editor's font tool and to send with `xstr`. The editor turns it into the two icon fonts (24 and 18 px).

## Adding a wallpaper
1. Put the image in `design/wallpapers/` and give it a name in `wallpaper_names.json`.
2. `python3 design/build_assets.py`: new pictures and a new manifest.
3. Import the new pictures into `firmware/glass.hmi` in manifest order (`tools/editor/import_pics.py <first new index>`),
   compile, export the `.tft` and flash it ([03](03-custom-firmware.md)).
4. Copy `design/assets/manifest.json` to `pi/display/glass/manifest.json`, and restart the display service.

The wallpaper can't be patched into an existing `.tft`: the display verifies the file
([03](03-custom-firmware.md#the-display-checks-the-file)).

## Testing without hardware
```bash
python3 -m unittest discover -s tests          # protocol builders, TJC driver, UI logic (fake display + API)
cd design && python3 mockups.py                # every screen as PNG
```
