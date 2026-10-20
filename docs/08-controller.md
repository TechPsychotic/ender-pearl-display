# Desktop controller

A GNOME app (GTK 4 / libadwaita) for your PC that reaches the printer's display through the Pi:
over Wi-Fi to the Ender Pearl web API, and over SSH for the rest.

| Live | Design | Flash | Service |
|---|---|---|---|
| ![Live](images/controller-live.png) | ![Design](images/controller-design.png) | ![Flash](images/controller-flash.png) | ![Service](images/controller-service.png) |

## Design: build screens without code
![Design](images/controller-design.png)

Make a screen for the printer from what is already in the display's firmware (no new firmware, no code):
- **Elements**, from the **+** menu:
  - glass panels (normal or focused);
  - text in five fonts;
  - any of the 61 icons;
  - progress bars, filled boxes, lines and circles;
  - the stored pictures (logo, boot frames).

  The wallpaper is picked in the toolbar.
- **Editing:**
  - Drag elements on the screen to move them, and drag the pink corner handle to resize.
  - Arrow keys nudge (Shift: 10 px), Delete removes, Ctrl+Z / Ctrl+Shift+Z undo and redo, Ctrl+D duplicates.
  - The list on the right orders them: later elements are drawn on top.
- **Settings:** each element's position, size, text, font, colour (with the theme's colour presets), alignment,
  and what is behind it. Text and icons blend with the panel or wallpaper behind them, chosen automatically.
- **Check:** the designer warns about what the display would do differently from what you'd expect:
  - text wider than its box (the display wraps it);
  - a box lower than its font;
  - characters a font doesn't have;
  - elements off the screen.
- **Live on the printer:** switch it on and the real display redraws after every change, in about half a second
  for a typical screen. It works through the bench, so the Ender Pearl screen pauses until you switch Live off.
- **What can the display do?** shows every icon and font as the display draws them, plus a plain-language list of
  the wallpapers, pictures, colours, shapes and limits, and what would need a new firmware.

  ![Capabilities](images/controller-capabilities.png)
- **Templates:** header and card, big number, tile menu, splash. Each shows a technique you can copy.
- **Commands:** the exact TJC instructions the screen sends, and the same screen as Python calls on the Pi app's
  canvas (`c.panel(…)`, `c.text(…)`), to paste into `pi/display/glass/app.py`.
- **Saving:** designs save and open as JSON files (`~/.config/ender-pearl-controller/designs` by default).

The designer draws through the Pi app's own canvas code (`pi/display/glass/canvas.py`), so the instructions are
exactly what the display app would send. The preview uses the repo's own pictures and fonts, so it works without
the Pi; Live and the other tabs need it.

## What it does
- **Live**
  - The printer's screen, mirrored live: it replays the display's own drawing commands with its own pictures and
    fonts.
  - The knob: buttons, the arrow keys / Enter / Esc, or the scroll wheel over the screen.
  - Wallpaper, brightness, sleep time, 12/24-hour clock, sending a message, jumping to a screen.
  - The printer's state and temperatures.
- **Flash**
  - Ask the display what it is: model, runtime version, flash size. This writes nothing.
  - Flash a `.tft` with a progress bar: the file goes to the Pi by `scp`, then `flash.py` sends it over UART3.
  - Put Creality's firmware back.
  - Flashing is only offered while the printer is idle.
- **Bench**
  - Pauses the display service, then sends raw TJC instructions and shows every reply: ok, the error name, a
    number or a string.
  - Has presets for quick tests. Stopping the bench, or closing the app, starts the service again.
- **Service**
  - Display service state with start / stop / restart buttons.
  - The web server's state, with a guarded restart that is refused while printing.
  - UART3 and its serial port, the last link message, and the display log, live.

## Install
Requirements on the PC:
- PyGObject with GTK 4 and libadwaita ≥ 1.5 (Fedora / Ubuntu 24.04+ GNOME have them);
- Pillow;
- `ssh` with key access to the Pi.

```bash
python3 tools/controller/ender_pearl_controller.py      # run it
tools/controller/install.sh                             # add "Ender Pearl Display" to the app list
```

The first time, open the connection menu (top left) and enter the Pi's host or IP, the SSH user and the project
folder. **Find the Pi** pings the local network and picks the Pi by its MAC address, which helps when its DHCP
address changes. Settings are saved in `~/.config/ender-pearl-controller/config.json`. The API token is read
from the Pi over SSH each time and never saved on the PC.

## How it talks to the Pi
| Feature | Path |
|---|---|
| mirror | `GET /api/display/frame`, pictures and fonts from `GET /api/display/asset` (cached in `~/.cache/ender-pearl-controller`) |
| knob | `POST /api/display/input` → a datagram to the display app on the Pi's `127.0.0.1:47321` |
| settings, message, go to a screen | `POST /api/display/config` |
| state | `GET /api/state` |
| flash, probe, restore | `scp` + `pi/display/flash.py` over SSH |
| bench | `systemctl --user stop ender-loop-display`, then `pi/display/bench.py` over SSH (stdin → display, replies as JSON lines) |
| design live | the bench's batch mode: one JSON line per redraw, `{"batch": [instructions]}`, sent pipelined (6 in flight) |
| service, log | `systemctl --user …`, `tail -F out/display.log` over SSH |

All SSH commands share one connection (OpenSSH `ControlMaster`), so a command takes ~35 ms after the first.
