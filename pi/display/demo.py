"""Bench test with the display wired to the Pi (DISPLAY_RE.md step 3): handshake, then an Ender Loop test screen
and a live knob readout (turn = counter, press = invert the box). Ctrl+C restores a blank screen.

    python3 display/demo.py --dry        # print the frames only (no display needed)
    python3 display/demo.py              # UART3 + knob on GPIO19 (A), GPIO26 (B), GPIO13 (ENTER)
    python3 display/demo.py --send-only  # display TX not wired (no resistors yet): skip waiting for its "OK" """
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import protocol as D  # noqa: E402

GREY, DARK, ACCENT = D.rgb565(40, 44, 52), D.rgb565(16, 18, 22), D.rgb565(34, 197, 94)
KNOB_A, KNOB_B, KNOB_ENTER = 19, 26, 13


def screen(count=0, pressed=False):
    f = [D.clear(DARK), D.colors(GREY, DARK), D.fill_rect(0, 0, 239, 24),
         D.text(8, 4, "Ender Loop", D.FONTS["8x16"], D.WHITE, GREY),
         D.text(8, 40, "Display test", D.FONTS["12x24"], D.WHITE, DARK),
         D.colors(ACCENT, DARK), D.rect(8, 80, 231, 140),
         D.text(20, 96, f"knob {count:+4d}", D.FONTS["16x32"], ACCENT, DARK)]
    if pressed:
        f.append(D.invert_rect(9, 81, 230, 139))
    f += [D.text(8, 300, time.strftime("%H:%M:%S"), D.FONTS["8x16"], D.WHITE, DARK)]
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--port")
    ap.add_argument("--send-only", action="store_true", help="display TX not connected: send the handshake but don't wait for the reply")
    a = ap.parse_args()
    if a.dry:
        for fr in screen(3, True):
            print(fr.hex(" "))
        return
    import gpio
    import link
    d = link.Display(a.port)
    if a.send_only:
        print(f"display on {d.port}: send-only (no reply expected); if the screen stays unchanged, check Pi pin 7 → display RX, GND, 5 V")
        d.send_only_init()
    else:
        print(f"display on {d.port}: handshake ", end="", flush=True)
        if not d.handshake():
            sys.exit("no answer: check TX/RX (crossed?), GND, 5 V, and the baud rate (or use --send-only if display TX isn't wired)")
        print("OK")
    d.send(D.backlight(48), *screen())
    q, count, pressed = gpio.Quadrature(), 0, False
    with gpio.Lines([KNOB_A, KNOB_B, KNOB_ENTER], pull="up", debounce_us=1000) as L:
        v = L.values(); q.feed(v[KNOB_A], v[KNOB_B])
        try:
            while True:
                if not L.events(0.5):
                    continue
                v = L.values()
                step = q.feed(v[KNOB_A], v[KNOB_B])
                p = v[KNOB_ENTER] == 0   # switch to GND
                if step or p != pressed:
                    count += step; pressed = p
                    box = [D.colors(DARK, DARK), D.fill_rect(9, 81, 230, 139), D.text(20, 96, f"knob {count:+4d}", D.FONTS["16x32"], ACCENT, DARK)]
                    d.send(*box, *([D.invert_rect(9, 81, 230, 139)] if p else []))
        except KeyboardInterrupt:
            d.send(D.clear(D.BLACK))
    d.close()


if __name__ == "__main__":
    main()
