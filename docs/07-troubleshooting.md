# Troubleshooting and lessons learned

| Symptom | Cause | Fix |
|---|---|---|
| `flash.py --probe`: no `comok` | wrong baud, or TX/RX swapped | try `--baud 921600` (our firmware after the app ran) and `--baud 115200` (stock / after power-up). Pi TX (pin 7) goes to the display's **RX** |
| Nothing on `/dev/ttyAMA*` | UART3 not enabled | `dtoverlay=uart3` in `/boot/firmware/config.txt`, reboot |
| Garbage at 115200 on `/dev/ttyS0` | that's the mini UART with the login console on it | use UART3 |
| Display shows **"System Data ERROR!"** | a modified / corrupt `.tft` (the display checks it) | flash a good build again over UART. If the display won't talk, use the microSD route |
| Display error `0x24` | commands sent faster than the display can take them | `bkcmd=3` and wait for replies (the canvas keeps ≤ 6 in flight) |
| Text breaks onto a second line | the display wraps text wider than its box | measure with the real glyph widths (`metrics.json`) and fit or scroll it |
| Values blink when they change | the whole panel was repainted | draw the panel once; update the text only, with `sta=0` crop (1–2 commands) |
| A box stays empty | drawn before its data arrived, and the signature didn't change | include the loaded data in the element's signature |
| Screen blank after plugging back onto the mainboard | our firmware doesn't speak Creality's protocol | flash the stock `tjc.tft` back first |
| No beep | this display's buzzer is silent even with 3.3 V on BEEP | an active 3.3 V buzzer on a Pi GPIO |
| Editor won't start: `load dll error: ApplicationRUN.resources` | only .NET 4 in the Wine prefix | install .NET 3.5 SP1 (the .NET 2.0 runtime) too |
| Scripted clicks do nothing in the editor (GNOME) | synthetic X input is blocked for XWayland windows | send input from Windows Python inside the Wine prefix (`tools/editor/winpy`) |
| Display service never starts at boot | systemd ordering cycle with the server's unit | don't put `After=default.target` in a unit that another `WantedBy=default.target` unit orders itself after |
| Knob turns the wrong way | wiring / taste | `KNOB_DIR = -1` in `glass_main.py` |

## Things we chose not to do
- **Decrypt or patch the TJC editor.** It runs fine under Wine as shipped.
- **Reverse engineer the `.tft` checksums.** A rebuild in the editor is the supported way to change pictures.
- **Ship Creality's display firmware.** It's theirs. Download it from Creality.
