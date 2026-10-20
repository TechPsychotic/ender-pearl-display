"""display/: the rest of the TJC3224 command set, the frame parser (sniffer) and the knob decoder (2026-10-18)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pi", "display"))
import gpio  # noqa: E402
import protocol as D  # noqa: E402

hx = lambda s: bytes.fromhex(s.replace(" ", ""))


class Commands(unittest.TestCase):
    def test_layouts(self):   # byte layouts of jpcurti's working driver (TJC3224.py)
        self.assertEqual(D.clear(0x0841), hx("AA 40 FF FF 08 41 CC 33 C3 3C AA 52 CC 33 C3 3C"))
        self.assertEqual(D.line(0, 25, 239, 25), hx("AA 51 00 00 00 19 00 EF 00 19 CC 33 C3 3C"))
        self.assertEqual(D.point(5, 6), hx("AA 51 00 05 00 06 CC 33 C3 3C"))
        self.assertEqual(D.invert_rect(1, 2, 3, 4), hx("AA 5C 00 01 00 02 00 03 00 04 CC 33 C3 3C"))
        self.assertEqual(D.backlight(99), hx("AA 5F 40 CC 33 C3 3C"))
        self.assertEqual(D.text(8, 4, "Hi", 2, 0xFFFF, 0x0000, True), hx("AA 98 00 08 00 04 00 42 02 FF FF 00 00 48 69 CC 33 C3 3C"))
        self.assertEqual(D.text(8, 4, "Hi", 2, 0xFFFF, 0x0000, False)[7], 0x02)
        self.assertEqual(D.icon_lib(0x0D, 0x78, 6, 8), D.icon(0x0D, 0x78, 0x0600, 8))
        self.assertEqual(D.picture(1), hx("AA 70 01 CC 33 C3 3C"))

    def test_text_ascii_only(self):   # the display font is ASCII; anything else becomes '?', so the tail can't appear
        self.assertEqual(D.text(0, 0, "°C")[-6:-4], b"?C")


class Parser(unittest.TestCase):
    def test_stream(self):
        boot = hx("00 11 AA 00 CC 33 C3 3C AA 3D CC 33 C3 3C AA 97 00 14 00 60 1B 01 00 08 CC 33 C3 3C AA 40 11")
        frames, rest = D.parse(boot)
        self.assertEqual([c for c, _ in frames], [0x00, 0x3D, 0x97])
        self.assertEqual(rest, hx("AA 40 11"))
        self.assertEqual(D.describe(*frames[2]), "icon x=20 y=96 lib=27 bg=1 id=8")
        frames2, rest2 = D.parse(rest + hx("45 FF FF CC 33 C3 3C"))
        self.assertEqual(D.describe(*frames2[0]), "colors fg=1145 bg=FFFF")
        self.assertEqual(rest2, b"")

    def test_handshake_reply(self):
        self.assertTrue(D.is_handshake_reply(hx("FF AA 00 4F 4B 00 01 CC 33 C3 3C")))
        self.assertFalse(D.is_handshake_reply(hx("AA 00 CC 33 C3 3C")))


class Knob(unittest.TestCase):
    def run_seq(self, seq):
        q = gpio.Quadrature()
        return [q.feed(a, b) for a, b in seq]

    def test_directions(self):
        cw = [(0, 0), (0, 1), (1, 1), (1, 0), (0, 0)]
        self.assertEqual(sum(self.run_seq(cw * 3)), 3)
        self.assertEqual(sum(self.run_seq(list(reversed(cw)) * 2)), -2)

    def test_bounce_and_skips(self):
        bouncy = [(0, 0), (0, 1), (0, 0), (0, 1), (1, 1), (1, 0), (1, 1), (1, 0), (0, 0)]
        self.assertEqual(sum(self.run_seq(bouncy)), 1)
        self.assertEqual(sum(self.run_seq([(0, 0), (1, 1), (0, 0), (1, 1)])), 0)   # impossible jumps are ignored

    def test_ioctl_sizes(self):
        self.assertEqual(gpio.GET_LINE, 0xC250B407)
        self.assertEqual(gpio.GET_LINEINFO, 0xC100B405)


if __name__ == "__main__":
    unittest.main()
