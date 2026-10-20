"""Glass UI theme: colours, font roles, sizes. Shared by the display app (Pi) and the mockup renderer (laptop).

Font roles map to TJC font ids in our firmware (assets/manifest.json "fonts"); the laptop renderer maps the same roles
to Inter / Lucide TTF files at the matching pixel size."""


def rgb(r, g, b):
    """RGB888 -> RGB565 number (what TJC commands take)."""
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


W, H = 240, 320
# colours as RGB tuples (the TJC canvas converts them)
TEXT = (236, 242, 245)
DIM = (150, 165, 172)
FAINT = (95, 110, 118)
TEAL = (45, 212, 191)          # accent: light teal green
TEAL_TEXT = (153, 246, 228)
TEAL_EDGE = (120, 230, 215)
EDGE = (70, 90, 98)            # top highlight line of a panel
TRACK = (30, 44, 48)           # empty part of bars
WARN = (251, 191, 36)
BAD = (248, 113, 113)
GOOD = (74, 222, 128)
PREVIEW_DONE = (45, 212, 191)
PREVIEW_TODO = (60, 80, 86)

# font roles: name -> (TJC font height in px, TTF face, characters)
ASCII = "".join(chr(c) for c in range(32, 127))
EXTRA = "°·‹›…–×"
FONTS = {
    "small": (14, "Inter-Regular", ASCII + EXTRA),       # captions
    "label": (18, "Inter-Regular", ASCII + EXTRA),       # rows, labels
    "body": (20, "Inter-Medium", ASCII + EXTRA),         # titles, focused rows
    "value": (40, "Inter-SemiBold", ASCII + EXTRA),      # temperatures, values
    "big": (64, "Inter-SemiBold", "0123456789%.:-+ "),   # big progress number
    "icon": (24, "epicons", None),                        # icons (characters from icons.json)
    "icon_s": (18, "epicons", None),
}
FONT_ORDER = ["small", "label", "body", "value", "big", "icon", "icon_s"]   # TJC font ids 0..6

HEADER_H = 30
PAD = 10
RADIUS = 9
ROW_H = 34
ROW_GAP = 5
