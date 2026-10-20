# The stock protocol (Creality's firmware on the display)

Only needed if you want to drive the display **without** flashing it, for example as a fallback, or to understand
what the mainboard does. With our firmware the display speaks TJC's text instructions instead ([04](04-drawing.md)).
Byte layouts follow jpcurti's notes and his working driver. `pi/display/protocol.py` builds and parses them, and
its frames were checked on our display.

## Framing
```
AA <cmd> <payload …> CC 33 C3 3C          115200 8N1, numbers big-endian 16-bit, colours RGB565
```
Like the DWIN T5L instruction set, but not identical. Coordinates as logged by the mainboard are portrait
(x 0–239, y 0–319).

## Commands (host → display)
| Bytes | Meaning |
|---|---|
| `AA 00` | handshake. The display answers `AA 00 'O' 'K' …`: a safe wiring test that draws nothing (`AA 3D` is also sent at boot) |
| `AA 40 <fg> <bg>` | set the current colours (RGB565) |
| `AA 52` | clear the screen with the background colour (send `AA 40` first) |
| `AA 5B <x0> <y0> <x1> <y1>` | filled rectangle in the current colour |
| `AA 59 <x0> <y0> <x1> <y1>` | rectangle outline |
| `AA 51 …` | line / point |
| `AA 5C <x0> <y0> <x1> <y1>` | invert an area (the stock menus' highlight) |
| `AA 5F <0–64>` | backlight |
| `AA 70 <id>` | show a stored full-screen picture |
| `AA 97 <x> <y> <lib/flags> <icon>` | draw a stored icon. Libraries: 0 icons, 4 English text, 27 animations … |
| `AA 98 <x> <y> 00 <mode> <size> <fg> <bg> <ascii…>` | **free text** in one of 9 built-in bitmap fonts (8 × 8 … 32 × 64) |
| `AA 09 82/83 <dy> <colour> <x0> <y0> <x1> <y1>` | scroll a region up / down |

Most menu "text" in Creality's UI is icons from library 4, so icon ids depend on the display firmware version.
Free text (`AA 98`) works without any icon table, which is what our first Pi UI (`pi/display/ui.py`) used.

## Tools in this repo
| File | Use |
|---|---|
| `pi/display/protocol.py` | frame builder, `parse()` (byte stream → frames), `describe()` |
| `pi/display/link.py` | UART3 at 115200, `handshake()` |
| `pi/display/sniff.py` | listen-only logger: tap the display's RX line and log what the mainboard draws, with a summary of every icon used |
| `pi/display/demo.py` | bench test: test screen and live knob counter (`--send-only` if display TX isn't wired, `--dry` prints frames) |
| `pi/display/gallery.py` | page through the stored icon libraries |
| `pi/display/ui.py` | the first Pi UI in this protocol (status, files, prepare, tune), superseded by the glass UI |

## The TJC side door
The same display also answers TJC's **upload handshake** while running Creality's firmware:
```
host:    FF FF FF  "DRAKJHSUYDGBNCJHGJKSHBDN" FF FF FF  "connect" FF FF FF
         (the long string leaves TJC's "protocol reparse" mode, in case the firmware uses it)
display: "comok 0,30599-0,TJC3224T132_011N,37,61760,…,8388608" FF FF FF
          ^touch  ^         ^model            ^fw ^       ^flash size
```
This is what made the custom firmware possible: see [03-custom-firmware.md](03-custom-firmware.md).
