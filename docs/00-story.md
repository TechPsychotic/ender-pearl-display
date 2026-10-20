# The story: how we got from Creality's menus to our own firmware

This is the path as it happened (16–20 October 2026), dead ends included. The technical details are in the other
documents; this one explains *why* each step was taken.

## 1. The starting point
The printer is an Ender-3 V3 SE with stock Marlin. A Raspberry Pi 4 runs a host project ("Ender Loop", later
renamed Ender Pearl): a web slicer, a G-code streamer that watches every layer, printer controls and a print queue.
The printer's screen still showed Creality's menus and knew nothing about the Pi. Options we weighed:

| | Idea | Verdict |
|---|---|---|
| A | Leave the screen on the mainboard, send `M117` messages | Works, but one line of text is all you get |
| **B** | **Move the display cable to the Pi and drive the screen from there** | **Chosen**: nothing to flash on the mainboard, fully reversible by plugging the cable back |
| C | Klipper on the mainboard (jpcurti's project drives the screen through the mainboard) | Would throw away the stock Marlin setup the host relies on |
| D | Patch Creality's closed Marlin to forward the screen | Closed source, brick risk |

## 2. Learning the stock protocol (plan B, phase 1)
jpcurti's notes showed that Creality's screen speaks a DWIN-T5L-like binary protocol at 115200 baud
(`AA <cmd> … CC 33 C3 3C`). Most of the stock "text" is in fact pre-rendered pictures stored in the display. We
wrote a frame builder (`pi/display/protocol.py`), a listen-only sniffer and a bench demo before touching any wire.

**Measuring before wiring.** The Pi's GPIO is 3.3 V only, so every line was measured with the printer on:
- knob lines A, B and ENTER at rest: 3.14 V (the mainboard's pull-ups);
- display TX: 3.34 V on the bench (3.3 V logic);
- BEEP: idle at 0 V.

Everything could go straight to the Pi.

**One surprise:** the Pi's primary UART carries the Linux login console, and the other one (the mini UART) changes
its baud rate with the CPU clock. So the display went on the Pi 4's spare PL011 **UART3** (GPIO4/5) instead.

With that, a send-only bench test drew on the screen, then the two-way link answered the handshake, and a first UI
in Creality's protocol ran: status, files, prepare, tune. It worked, but it looked like what it was: stock icons
and fixed bitmap fonts.

## 3. The turn: it's a TJC display, and it accepts uploads (plan C2)
Creality's official firmware package contains the display's firmware as `TJC_SET/tjc.tft`. That's a project for
TJC's own editor (TJC is the Chinese sister brand of Nextion). If we could build our own `.tft`, the screen
could hold *our* fonts and pictures, and the Pi could draw anything with TJC's documented instruction set.

Three things had to work out:
1. **The editor runs on Linux.** TJC's USART HMI editor is Windows-only and ships encrypted, so it can't be ported.
   It runs under Wine with .NET 3.5 and .NET 4.8 installed. GNOME blocks synthetic input to Wine windows, so to script it
   we run Windows Python *inside* the same Wine prefix ([docs/03](03-custom-firmware.md#the-editor-under-wine)).
2. **Our build matches the model.** A test project built for TJC3224T132_011 has the same family, version,
   resolution and model bytes in its header as Creality's file.
3. **No SD card needed.** The display answers TJC's standard upload handshake (`connect` → `comok …`) **even while
   running Creality's firmware**, on the wires we had already connected. The reply named the model
   (TJC3224T132_011N) and the flash size (8 MB). So the Pi can flash it directly.

The first upload (a test project with one font) took 37 s at 115200 baud. The display rebooted into it, and the Pi
drew text, rectangles and a circle with TJC commands. Every command was acknowledged.

## 4. One rule we found the hard way
Pictures sit in a `.tft` as raw RGB565, so it looked as if the Pi could swap a wallpaper by patching the file. It
can't: the display checks the file's checksums. A patched build uploaded fine and then booted to
**"System Data ERROR!"**. Re-flashing the unpatched build over the same serial line recovered it. We deliberately
did **not** reverse engineer TJC's checksum scheme. New pictures mean a rebuild in the editor.

## 5. Designing the glass UI
The display can't do transparency or blur at run time, but it can copy any rectangle of a stored picture onto the
screen (`xpic`) and draw anti-aliased text whose background is copied from a picture (`xstr`, background mode
"crop"). That is enough for a glass look:
- every wallpaper is stored three times: plain, "glass" (blurred, darkened, faint teal) and "focus" (lighter);
- a panel is the matching rectangle of the glass picture, with rounded corners made by copying the plain
  wallpaper back into the corner pixels, and a 1-px highlight line;
- text is drawn over the panel with its background cropped from the same picture, so the anti-aliasing blends.

The same app code renders the PNG mockups on the laptop (a Pillow canvas) and drives the real display (a TJC
canvas), so every screen could be designed and reviewed before it ever touched hardware
([docs/images/screens.png](images/screens.png)).

## 6. Making it feel right
Real use turned up a few problems:
- **Display buffer overflow:** at 921600 baud, sending commands as fast as possible overflowed the display's input
  buffer (error 0x24). Now every command is acknowledged (`bkcmd=3`) and at most six are in flight at once.
- **Text wrapping:** the display wraps text that is wider than its box. The app now reads each glyph's exact width
  from the font files and fits or scrolls text itself.
- **Blinking:** a changed number used to repaint its whole panel (about 45 commands). Now the panel is drawn once and
  only the changed text is redrawn (1–2 commands), so values update without a blink.
- **Bad progress readings:** progress counted G-code lines, which hit 100 % with layers still to print. It now uses
  time, and never shows 100 % before the end.
- **Silent beeper:** the beeper line from the display goes to the Pi, but the display's buzzer turned out to be silent
  even with 3.3 V applied. A small active buzzer on the Pi is the fix if we ever want sound.

## 7. Where it ended up
- **Start-up:** the screen starts at boot with the Pi, and restores its wallpaper and brightness even before the
  web server is up.
- **Sleep:** it sleeps with the backlight off, and wakes on the knob, a message or a print. It stays on while
  printing.
- **Live preview:** the web UI shows a live copy of what the screen shows (the app records its drawing commands and
  the browser replays them).
