"""Browse the pictures stored in the display (icon libraries) and measure its fonts, with the knob.

Icon numbers depend on the display firmware, so ours have to be looked at: each page shows 4 icons in a 2 x 2 grid,
labelled "L<library> #<id>". Turn = next / previous page, press = next library. The last "library" is a font test page
(every built-in size, with a 10 px ruler) to measure the real character sizes.

    systemctl --user stop ender-loop-display-test     # the UI holds the display and knob
    python3 display/gallery.py [--lib 0] [--start 0]"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gpio  # noqa: E402
import link  # noqa: E402
import protocol as D  # noqa: E402

LIBS = [0, 1, 2, 3, 4, 5, 6, 27, "fonts"]
BG, GRID, LABEL = D.rgb565(60, 60, 70), D.rgb565(120, 120, 130), D.rgb565(255, 230, 80)
CELL_W, CELL_H, PER_PAGE = 120, 148, 4


def icon_page(lib, start):
    f = [D.clear(BG), D.colors(D.rgb565(30, 30, 36), BG), D.fill_rect(0, 0, 239, 19),
         D.text(4, 2, f"library {lib}: #{start}-#{start + PER_PAGE - 1}", D.FONTS["8x16"], D.WHITE, BG, False)]
    for k in range(PER_PAGE):
        cx, cy = (k % 2) * CELL_W, 22 + (k // 2) * CELL_H
        f += [D.colors(GRID, BG), D.rect(cx, cy, cx + CELL_W - 1, cy + CELL_H - 1),
              D.icon_lib(cx + 4, cy + 4, lib, start + k, False),
              D.colors(BG, BG), D.fill_rect(cx + 1, cy + CELL_H - 17, cx + CELL_W - 2, cy + CELL_H - 2),
              D.text(cx + 4, cy + CELL_H - 16, f"L{lib} #{start + k}", D.FONTS["8x16"], LABEL, BG, False)]
    return f


def font_page():
    f = [D.clear(D.BLACK), D.colors(D.rgb565(90, 90, 90), D.BLACK)]
    for y in range(0, 320, 10):   # ruler: a tick every 10 px, longer every 50
        f.append(D.line(0, y, 9 if y % 50 else 19, y))
    for x in range(20, 240, 10):
        f.append(D.line(x, 0, x, 4 if x % 50 else 9))
    y = 14
    for size in range(9):
        w, h = D.FONT_PX[size]
        if y + h > 318:
            break
        f += [D.colors(D.rgb565(0, 90, 160), D.BLACK), D.fill_rect(22, y, 22 + 4 * w - 1, y + h - 1),   # where the docs say 4 chars go
              D.text(22, y, "Ag08", size, D.WHITE, D.BLACK, False),
              D.text(150, y, f"s{size} {w}x{h}", D.FONTS["6x12"], LABEL, D.BLACK, False)]
        y += h + 4
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lib", type=int, default=0)
    ap.add_argument("--start", type=int, default=0)
    a = ap.parse_args()
    d = link.Display()
    if not d.handshake():
        sys.exit("display didn't answer the handshake")
    li, start = LIBS.index(a.lib) if a.lib in LIBS else 0, a.start

    def show():
        d.send(*(font_page() if LIBS[li] == "fonts" else icon_page(LIBS[li], start)))
        print(f"showing {LIBS[li]} {start}", flush=True)

    show()
    q = gpio.Quadrature()
    with gpio.Lines([19, 26, 13], pull="up", debounce_us=1000) as L:
        v = L.values(); q.feed(v[19], v[26]); pressed = v[13] == 0
        while True:
            if not L.events(1.0):
                continue
            v = L.values()
            step = q.feed(v[19], v[26])
            p = v[13] == 0
            if step and LIBS[li] != "fonts":
                start = max(0, start + step * PER_PAGE); show()
            if p and not pressed:
                li = (li + 1) % len(LIBS); start = 0; show()
            pressed = p


if __name__ == "__main__":
    main()
