# Drawing a glass UI with plain TJC instructions

With our firmware the display has no UI of its own. The Pi sends text instructions, each ended by `FF FF FF`.

## The instructions we use
| Instruction | Use |
|---|---|
| `xpic x,y,w,h,sx,sy,pic` | copy a rectangle of a stored picture to the screen: panels, wallpaper restore, rounded corners |
| `xstr x,y,w,h,font,fg,bg,xcen,ycen,sta,"text"` | text in a box. `sta` = background: 0 crop from picture `bg`, 1 solid colour, 2 picture, 3 none |
| `fill x,y,w,h,colour` | bars, solid areas |
| `line x0,y0,x1,y1,colour` | panel highlights, 3D previews, mesh grid |
| `pic x,y,id` | whole pictures (boot frames) |
| `dim=0..100` | backlight (0 = off: sleep) |
| `baud=921600`, `bkcmd=3` | link speed, and a reply to every command (used for flow control) |
| `tm0.en=0` | stop the firmware's own boot-animation timer |
| `get dim` | "are you there?": the reply starts with `0x71` |

Colours are RGB565 numbers (`pi/display/glass/theme.py: rgb()`).

## The glass look without blur
The display can't blend or blur at run time, so the effect is baked in:
1. **Three versions of each wallpaper** in the firmware, 240 × 320 each: `bg` (the image), `glass` (blurred,
   darkened, a faint teal tint) and `focus` (lighter, more teal, for the selected item).
2. **A panel** is `xpic` of the same rectangle from the `glass` picture. On screen it looks like frosted glass over
   the wallpaper, because it *is* the wallpaper, pre-blurred.
3. **Rounded corners**: for each row of the corner radius, copy the plain `bg` picture back over the pixels outside
   the arc (`canvas.panel()`).
4. **A 1-px highlight line** along the top edge (teal when focused).
5. **Anti-aliased text** with `xstr … sta=0` and `bg` = the glass picture. The display fills the text box from the same
   picture before blending the glyph edges, so the anti-aliasing matches the panel exactly. (With `sta=3` the edges
   are jagged; with `sta=1` they need a solid background colour.)

Switching wallpaper is just switching which three picture ids the canvas uses.

## Flow control at 921600 baud
Sending commands back to back at 921600 overflows the display's input buffer (error `0x24`). With `bkcmd=3` the
display answers every command: `0x01` = done, otherwise an error code. `canvas.TjcCanvas` keeps at most
**6 commands in flight** and reads replies before sending more. Errors are counted, not fatal. If replies time out,
it starts the count over.

| Reply | Meaning |
|---|---|
| `01` | ok |
| `02` / `03` / `04` / `05` | invalid component / page / picture / font |
| `1A` | invalid variable |
| `1E` | wrong parameter count |
| `24` | serial buffer overflow |

## Text that fits
The display wraps text that is wider than its box onto the next line. So the app measures text itself:
`design/build_metrics.py` reads each glyph's advance width from the generated font files (`fonts/*.zi`: glyph count
at `0x0C`, then 10-byte entries `u16 code, u8 width, …`) into `pi/display/glass/metrics.json`. The app shortens text
with "…" (`fit`) or scrolls long names in a marquee (`window`). The parser keeps only tables whose characters are in
the font's character set; an earlier version picked a wrong table for the digits-only big font.

## Drawing only what changed
Each screen element is drawn through `App.el(key, signature, draw)`: it draws only when its signature (the values
it shows) changes. Boxes are split into a **box** (panel, icon, label: drawn once) and **values** (text only).

| | Commands per changed value | Looks like |
|---|---|---|
| repaint the panel, then the text | ~45 (37 picture strips for corners) | a blink every few seconds |
| text only, `sta=0` crop | 1–2 | the number changes in place |

If a box is repainted (for example on screen change), its values are forced to redraw too. Data that loads in the
background, such as a preview arriving after the first draw, is part of the signature, so it appears as soon as it
arrives.

## The live preview on the display
While printing, the screen shows the plate in 3D: printed layers in teal, the rest grey.
- **Paths:** the server prebuilds isometric paths for every job and caches them on disk (`server/display_api.py`).
- **Drawing:** the app draws them with `line`, grey first and teal on top, and redraws only when the layer changes.

## Mirror in the browser
`TjcCanvas` records every command since the last full redraw. `glass_main.py` writes that list to
`out/display_frame.json` about every 0.7 s. The web UI replays it on an HTML canvas with the same pictures and
fonts, which gives a live copy of the printer's screen in the browser.
