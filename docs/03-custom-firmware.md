# Custom firmware: building our own `.tft` and flashing it from the Pi

## The idea
A TJC display runs a "project" compiled by TJC's **USART HMI** editor into a `.tft` file: pages, components,
scripts, fonts and pictures. Ours is deliberately almost empty:

- **one blank page**, portrait 240 × 320, UTF-8;
- **7 fonts**, anti-aliased, generated from TTF files;
- **all the pictures** the UI needs: three per wallpaper, plus the boot-animation frames;
- **a timer** (`tm0`) that plays the boot animation on its own from power-up, until the Pi takes over;
- the serial port at 115200 after power-up; the Pi app switches it to 921600 (`baud=921600`) each time it connects.

The Pi draws everything else at run time with TJC's standard instructions. Layout and behaviour live in Python
on the Pi, so most changes don't need a re-flash.

| Font id | Role | Size | Face | Characters |
|---|---|---|---|---|
| 0 | small | 14 px | Inter Regular | ASCII + `°·‹›…–×` |
| 1 | label | 18 px | Inter Regular | same |
| 2 | body | 20 px | Inter Medium | same |
| 3 | value | 40 px | Inter SemiBold | same |
| 4 | big | 64 px | Inter SemiBold | `0123456789%.:-+ ` |
| 5 | icon | 24 px | our icon font (Lucide glyphs) | the icons in `pi/display/glass/icons.json` |
| 6 | icon_s | 18 px | same | same |

Picture ids are listed in `design/assets/manifest.json` (wallpaper → `bg`/`glass`/`focus` ids, font roles → font ids, boot frames).
The Pi app reads the same manifest, so the ids in the firmware and in the code always match.

## The editor under Wine
The editor is Windows-only. It ships **encrypted**: its DLLs are blobs unpacked at run time by a small .NET 2.0
stub, so there is no native Linux build and we did not try to make one. It runs well under Wine:

```bash
# Wine 11, a separate prefix; the stub needs the .NET 2.0 runtime (via 3.5 SP1) — on .NET 4 alone it fails with
# "load dll error: ApplicationRUN.resources"
export WINEPREFIX=~/.wine-tjc
winetricks -q dotnet35sp1 dotnet48 corefonts
wine USARTHMIsetup_1.68.1.exe          # TJC's installer, from tjc1688.com
tools/editor/run-editor.sh             # starts "USART HMI.exe" in that prefix
```

The editor's interface is Chinese only.

### Scripting the editor
We built the project by scripting the editor rather than clicking through it:
- **Input:** GNOME blocks synthetic X input (XTEST) into XWayland windows, so `tools/editor/winpy/winside.py`
  runs in **Windows Python inside the same Wine prefix**. Put the "Windows embeddable" Python zip in
  `tools/editor/winpy`. It sends real Windows input (`SendInput`), lists child windows and selects controls by
  handle.
- **Screenshots:** `tools/editor/xdrive.py` captures the Wine windows, dialogs included, through Xlib.
- **Wrapper:** `tools/editor/tjcui.py` wraps both: `shot`, `click X Y`, `text`, `key`.
- **Fonts:** `tools/editor/gen_fonts.py` drives the editor's font tool to generate the seven fonts (`fonts/*.zi`)
  and adds them to the project in id order.
- **Pictures:** `tools/editor/import_pics.py` imports the pictures one at a time, so their ids follow the manifest.

### Checking the model
A test project compiled for **TJC3224T132_011** (portrait 0, UTF-8) produced a header that matches Creality's
`tjc.tft` in the family/version bytes, the resolution, the model bytes at `0x2E–0x32`, and 120 of the last 124
bytes of the encrypted block (`0x114–0x18B`). The differences were size and checksum fields. Same model.

## Flashing over the serial line
The display answers TJC's upload handshake even under Creality's firmware, so the Pi flashes it over the same four
wires it draws with. No SD card is needed. `pi/display/flash.py` does it:

```bash
python3 pi/display/flash.py --probe                 # who are you? writes nothing
python3 pi/display/flash.py firmware/glass.tft      # flash our firmware
python3 pi/display/flash.py --stock                 # flash Creality's tjc.tft back
```

It stops the display service while flashing, checks the model is `TJC3224T132_011*` before writing anything, and
starts the service again afterwards.

The upload protocol, as implemented in `pi/display/tjc.py: upload()` (it is TJC/Nextion's documented one):

```
host → FF FF FF "DRAKJHSUYDGBNCJHGJKSHBDN" FF FF FF  "connect" FF FF FF        at the display's current baud
disp → "comok 0,30599-0,TJC3224T132_011N,37,61760,…,8388608" FF FF FF
host → "whmi-wri <file size>,<upload baud>,0" FF FF FF
        (switch the host's port to <upload baud>)
disp → 05                                   ready
host → 4096-byte block   disp → 05          … repeated until the whole file is sent
        the display verifies the file and restarts into it
```

- `--baud` is the display's *current* baud: 115200 under Creality's firmware or after a power cycle, 921600 while
  our app has been running. Uploads themselves run at 921600.
- The first test upload (395 KB at 115200) took **37 s**.
- If an upload is interrupted, just run it again: the display's bootloader is never written. The microSD route
  below is the last resort.

## The display checks the file
Pictures are stored raw in the `.tft`: RGB565 little-endian with a 44-byte header each. It looks as if you could
swap a picture by patching the file. **You can't.** Three 4-byte fields change with any pixel: offset `0x44`
(header), `0xC4` (start of the scrambled block) and the last 4 bytes. None of them is a standard CRC32. A patched
build uploads fine, then boots to **"System Data ERROR!"**. Flashing the unpatched build over UART recovered it.

We deliberately did not reverse engineer TJC's checksum scheme. New pictures (a new wallpaper, say) mean a rebuild
in the editor. That's why the wallpapers are built into the firmware and switched at run time.

## Building `glass.tft`
1. `design/build_assets.py` renders the wallpapers in `design/wallpapers/` (plus the procedural "neon bedgrid") into
   `design/assets/` (`*_bg`, `*_glass`, `*_focus`, 240 × 320) and writes `manifest.json`.
   `design/boot.py` adds the boot frames.
2. In the editor, open `firmware/glass.hmi`: model TJC3224T132_011, portrait, UTF-8. For a new project, set the page
   size to 240 × 320.
3. `tools/editor/gen_fonts.py` (fonts, in id order) and `tools/editor/import_pics.py 0` (pictures, in manifest order).
4. Compile, then export the `.tft` from the editor. Flash it with `flash.py`.
5. `design/build_metrics.py` reads the glyph widths from `fonts/*.zi` into `pi/display/glass/metrics.json`. The Pi uses
   them to fit text, because the display wraps text wider than its box.

`firmware/glass.tft` (sha256 `9e6abf0b…58bcb`) is the exact build running on our display.
`firmware/glass.hmi` (sha256 `4301ff19…c103b`) is its project file.

## Back to stock
Creality's display firmware isn't in this repo, because it isn't ours. It's in Creality's official firmware package
for the Ender-3 V3 SE, **V1.1.0 (2025-05-12)**: `屏幕固件/TJC_SET/tjc.tft`, 7,483,004 bytes,
sha256 `b1285d519ddf26fef386ea8dbf7a91e56b21a8b052caabeae384243f8693ccd0`.
Package link at the time of writing:
`https://file2-cdn.creality.com/file/751a1570d23607bd9503f690f7eefcbd/Ender-3%20V3%20SE_HWCR4NS200320C13C14_SWV1.1.0_GD303STM32F401.rar`

Two ways back:
- **Serial:** put the file at `out/stock_display_fw/TJC_SET/tjc.tft` (next to `pi/`, or edit `STOCK` in `flash.py`),
  then `python3 pi/display/flash.py --stock --baud 921600`.
- **SD card**, Creality's way, which also works if the display won't talk:
  1. Copy the `TJC_SET` folder to a FAT32 microSD card (4096-byte clusters).
  2. Insert the card in the **display's own** slot, with the ribbon connected.
  3. Power on and wait.

Community reports: display firmware 1.06 was reported as corrupt (1.04 used instead), and flashing another model's
display firmware has bricked screens. Only flash files built for the TJC3224T132_011.
