"""Release / social-preview banner (1280 x 640): logo, title, three real screens on the neon bedgrid wallpaper.
    python3 tools/release/banner.py   -> docs/images/banner.png"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(REPO, "design")
FONT = "/usr/share/fonts/rsms-inter-fonts/{}.ttf"
W, H = 1280, 640
TEAL, TEXT, DIM = (45, 212, 191), (236, 242, 245), (150, 170, 178)


def font(face, size):
    return ImageFont.truetype(FONT.format(face), size)


# background: the wallpaper, stretched, blurred and darkened, with a teal glow on the left
bg = Image.open(os.path.join(D, "assets", "neon-bedgrid_bg.png")).convert("RGB").resize((W, int(W * 320 / 240)))
bg = bg.crop((0, (bg.height - H) // 2, W, (bg.height - H) // 2 + H)).filter(ImageFilter.GaussianBlur(6))
img = Image.blend(bg, Image.new("RGB", (W, H), (6, 14, 18)), 0.55)
glow = Image.new("L", (W, H), 0)
ImageDraw.Draw(glow).ellipse((-260, -120, 640, 760), fill=110)
img = Image.composite(Image.new("RGB", (W, H), (20, 70, 66)), img, glow.filter(ImageFilter.GaussianBlur(120)))

# three screens, rounded, with a soft shadow; the middle one raised
shots = ["01_home_neon-bedgrid.png", "02_printing_neon-bedgrid.png", "24_mesh.png"]
sw, sh = 210, 280
xs, ys = [655, 885, 1055], [190, 150, 210]
order = [0, 2, 1]                     # the middle (printing) screen drawn last, on top
for k in order:
    s = Image.open(os.path.join(D, "mockups", shots[k])).convert("RGB").resize((sw, sh), Image.LANCZOS)
    x, y = xs[k] - (40 if k == 2 else 0), ys[k]
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((x + 6, y + 14, x + sw + 6, y + sh + 14), 18, fill=170)
    img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shadow.filter(ImageFilter.GaussianBlur(14)))
    mask = Image.new("L", (sw, sh), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, sw - 1, sh - 1), 14, fill=255)
    img.paste(s, (x, y), mask)
    ImageDraw.Draw(img).rounded_rectangle((x, y, x + sw - 1, y + sh - 1), 14, outline=(70, 110, 112), width=2)

# logo + text
logo = Image.open(os.path.join(D, "logo", "logo_128.png")).convert("RGBA")
img.paste(logo, (70, 92), logo)
d = ImageDraw.Draw(img)
d.text((70, 250), "Ender Pearl", font=font("Inter-Bold", 74), fill=TEXT)
d.text((72, 336), "Display", font=font("Inter-SemiBold", 44), fill=TEAL)
d.text((72, 410), "Custom TJC firmware and a Pi-driven glass UI", font=font("Inter-Regular", 24), fill=TEXT)
d.text((72, 442), "for the Creality Ender-3 V3 SE's own screen", font=font("Inter-Regular", 24), fill=TEXT)
tags = ["TJC3224T132", "Raspberry Pi 4", "UART flashing", "GPL-3.0"]
x = 72
for t in tags:
    f = font("Inter-Medium", 17)
    tw = d.textlength(t, font=f)
    d.rounded_rectangle((x, 510, x + tw + 26, 544), 17, fill=(18, 52, 52), outline=(45, 140, 128))
    d.text((x + 13, 527), t, font=f, fill=(153, 246, 228), anchor="lm")
    x += tw + 38
d.text((72, 590), "github.com/TechPsychotic/ender-pearl-display", font=font("Inter-Regular", 16), fill=DIM)
out = os.path.join(REPO, "docs", "images", "banner.png")
img.save(out, optimize=True)
print(out, img.size)
