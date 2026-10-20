# Ender Loop printer display: screens, menus and elements (v2, glass UI)

240 x 320 portrait. Knob: turn = move focus / change value, press = select / confirm. Long press (≥ 0.8 s) = back.
Every action goes through the web server's API (same checks as the browser). Items that need an idle printer are
greyed out while printing. Items marked ⚠ change stored printer settings or use filament: they always ask first.

## Building blocks (one renderer for mockups and the real display)
- **Header**: title (left), clock (right), status dots: Wi-Fi/server, printer link. Back hint "‹" on sub-screens.
- **Glass panel / row / tile**: cropped from the wallpaper's glass picture; focused = cropped from the focus picture
  with a teal edge line. Rounded corners.
- **List**: rows with icon, label, value (right) and "›" for sub-menus; scrolls with a thin scroll bar.
- **Value editor**: big value, unit, range bar, step hint; turn = change, press = set, long press = cancel.
- **Confirm dialog**: question, details, [Cancel] [Confirm]; Cancel focused first.
- **Message / toast**: one line at the bottom for 4 s; errors as a red-edged dialog.
- **Busy**: spinner + text while an action runs (homing, heating, levelling).
- **Live layer preview**: the current layer's toolpath, printed part teal, rest dim; redrawn per layer.

## Screens
1. **Home** (idle): nozzle and bed cards (temperature, target, heating bar), status line (idle / filament loaded /
   queue), tiles **Print · Prepare · Control · Level**. Widgets are chosen in the web UI.
2. **Print**
   - **From the Pi**: G-code files, newest first (modification time); each row: name, date, estimated time.
     → **File details**: name, estimated time, filament length, layers, material, sliced profile →
       **Start** (confirm: bed clear, filament family) · Back.
   - **From the SD card**: the printer's own card (M20 L), newest first by card order (the firmware gives no dates)
     → details (size) → **Start SD print** (confirm: bed clear) · **Delete** (confirm).
   - **Print queue**: queued jobs, **Start queue** (confirm bed clear) / **Next job** when waiting.
3. **Printing** (replaces Home while printing)
   - Progress card: file, big %, time left, done at, **elapsed**, progress bar.
   - **Live preview** panel (current layer) with layer n/N and Z.
   - Details: nozzle and bed (actual/target), **fan %**, **speed %**, **flow %**, filament used, resends.
   - Tiles: **Pause/Resume · Tune · Stop**. SD prints: Pause/Resume · Tune (temps/fan/speed/flow) · Stop.
   - **Tune**: Speed % · Flow % · Fan % · Nozzle °C · Bed °C · Z babystep · Skip object (list of objects, confirm).
   - **Stop**: confirm. **Finished**: summary (time, filament), [OK] → Home; queue alert "Clear the bed".
4. **Prepare** (idle)
   - **Home axes** → All · X · Y · Z.
   - **Move axes** → X · Y · Z → step 10 / 1 / 0.1 mm → jog screen (position live).
   - **Preheat** → PLA · PETG · Custom (nozzle + bed editors).
   - **Cool down**. **Fan** (value). **Nozzle temperature**, **Bed temperature** (values).
   - **Filament** → Load ⚠ · Unload ⚠ · Extrude 10 mm ⚠ · Retract 10 mm ⚠ (need a hot nozzle; shows temperature).
   - **Park head**. **Motors off**.
5. **Control**
   - **Display** → Wallpaper (list of built-in wallpapers, preview) · Brightness · Sleep after · Clock 12/24 h.
   - **Motion** → max speed / acceleration / jerk / steps (read from the printer; edits ⚠ save to EEPROM).
   - **Temperature** → PID values (read) · PID tune hotend ⚠ · PID tune bed ⚠.
   - **Store settings** ⚠ (M500) · **Restore settings** ⚠ (M501).
   - **Info** → web address (QR code), printer firmware, display firmware, print time logged, filament loaded,
     Pi temperature and uptime.
6. **Level**
   - **Bed mesh** (4 x 4 heat map with values, read from the printer).
   - **Auto level** ⚠ (confirm, busy for minutes, shows the new mesh).
   - **Z offset** (value editor in 0.01 mm, saves with M500 ⚠).
7. **Pop-ups**: queue alerts, watchdog alerts, print finished/failed, printer disconnected, server unreachable,
   web message ("Message from the web UI").

## Web UI control (Device ▸ Printer screen)
Wallpaper (built-in list + upload → queued firmware build on the laptop), home widgets, brightness, sleep,
clock format, push a message, show a screen, live preview of the display.
