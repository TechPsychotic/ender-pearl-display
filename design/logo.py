"""Ender Pearl logo: a portrait infinity symbol (lemniscate stood on end) whose top and bottom are cut flat and capped
with bars, so it reads as an hourglass rather than an 8. Drawn supersampled, teal gradient with a soft glow.

    python3 logo.py      -> logo/logo_<size>.png (transparent) and logo/preview.png"""
import math
import os

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "logo")
TEAL_A, TEAL_B = (45, 212, 191), (165, 250, 235)


def lemniscate(cx, cy, a, n=720, angle=90.0, squash=1.0):
    """Points of a lemniscate of Bernoulli centred at (cx, cy), half-length a, rotated by angle (90 = portrait)."""
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    pts = []
    for i in range(n + 1):
        t = 2 * math.pi * i / n
        d = 1 + math.sin(t) ** 2
        x, y = a * math.cos(t) / d, a * math.sin(t) * math.cos(t) / d * squash
        pts.append((cx + x * ca - y * sa, cy + x * sa + y * ca))
    return pts


def mark_mask(size, stroke=0.085, cap=0.90, angle=90.0, morph=1.0, squash=1.0):
    """White-on-black mask of the mark. morph 0 = plain infinity, 1 = flat-capped hourglass."""
    S = size * 4
    m = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(m)
    a = S * 0.42   # leaves room for the stroke when the mark lies horizontal
    w = int(S * stroke)
    pts = lemniscate(S / 2, S / 2, a, angle=angle, squash=squash)
    r = w / 2   # stamp round dots along the path: an even stroke without the gaps of a wide polyline
    dense = lemniscate(S / 2, S / 2, a, n=6000, angle=angle, squash=squash)
    for x, y in dense:
        d.ellipse([x - r, y - r, x + r, y + r], fill=255)
    if morph > 0 and abs(math.sin(math.radians(angle))) > 0.999:   # caps only once standing upright
        cut = S / 2 + a * cap                       # flat cut where the loops are cut off (fraction of the half-length)
        top, bot = S - cut, cut
        k = morph
        d.rectangle([0, 0, S, top - w / 2 * k], fill=0)             # cut both ends flat...
        d.rectangle([0, bot + w / 2 * k, S, S], fill=0)
        # ...and cap them with bars as wide as the loop there
        span = max(abs(x - S / 2) for x, y in pts if abs(y - top) < w * 0.6) + w / 2
        bar = span * (0.75 + 0.35 * k)
        for yy in (top, bot):
            d.rounded_rectangle([S / 2 - bar, yy - w / 2, S / 2 + bar, yy + w / 2], radius=w / 2, fill=255)
    return m.resize((size, size), Image.LANCZOS)


def colour(mask, glow=True):
    size = mask.size[0]
    grad = Image.new("RGB", (size, size))
    gd = ImageDraw.Draw(grad)
    for y in range(size):
        t = y / max(1, size - 1)
        gd.line([(0, y), (size, y)], fill=tuple(int(TEAL_B[k] + (TEAL_A[k] - TEAL_B[k]) * t) for k in range(3)))
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    if glow:
        g = mask.filter(ImageFilter.GaussianBlur(size / 28)).point(lambda v: int(v * 0.55))
        out.paste(Image.new("RGBA", (size, size), TEAL_A + (255,)), (0, 0), g)
    out.paste(grad, (0, 0), mask)
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    for s in (64, 96, 128, 512):
        colour(mark_mask(s)).save(os.path.join(OUT, f"logo_{s}.png"))
    # preview: the mark at 3 stages + the lockup with the name, on the dark background
    bg = (8, 12, 15)
    prev = Image.new("RGB", (900, 320), bg)
    for i, (ang, mo) in enumerate([(0, 0), (45, 0), (90, 0.0), (90, 0.5), (90, 1.0)]):
        mk = colour(mark_mask(150, angle=ang, morph=mo))
        prev.paste(mk, (20 + i * 175, 20), mk)
    f = ImageFont.truetype("/usr/share/fonts/rsms-inter-fonts/Inter-SemiBold.ttf", 44)
    mk = colour(mark_mask(110))
    prev.paste(mk, (300, 190), mk)
    ImageDraw.Draw(prev).text((420, 245), "Ender Pearl", font=f, fill=(225, 245, 242), anchor="lm")
    prev.save(os.path.join(OUT, "preview.png"))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
