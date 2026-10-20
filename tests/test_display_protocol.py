"""display/protocol.py reproduces the frames logged from the stock printer (jpcurti's reverse-engineering doc)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pi", "display"))
import protocol as D  # noqa: E402

hx = lambda s: bytes.fromhex(s.replace(" ", ""))


class Frames(unittest.TestCase):
    def test_logged_boot_frames(self):
        self.assertEqual(D.handshake(), hx("AA 00 CC 33 C3 3C"))
        self.assertEqual(D.colors(0x1145, 0xFFFF), hx("AA 40 11 45 FF FF CC 33 C3 3C"))
        self.assertEqual(D.fill_rect(0, 0, 0xEF, 0x18), hx("AA 5B 00 00 00 00 00 EF 00 18 CC 33 C3 3C"))
        self.assertEqual(D.fill_rect(0, 0x19, 0xEF, 0x13F), hx("AA 5B 00 00 00 19 00 EF 01 3F CC 33 C3 3C"))
        self.assertEqual(D.rect(0x0C, 0x33, 0x71, 0xA5), hx("AA 59 00 0C 00 33 00 71 00 A5 CC 33 C3 3C"))
        self.assertEqual(D.icon(0x0D, 0x78, 0x0600, 0x0008), hx("AA 97 00 0D 00 78 06 00 00 08 CC 33 C3 3C"))
        self.assertEqual(D.icon(0x14, 0x60, 0x1B01, 0x0008), hx("AA 97 00 14 00 60 1B 01 00 08 CC 33 C3 3C"))

    def test_scroll(self):
        self.assertEqual(D.scroll(True, 0x24, 0x0841, 0x0B, 0x19, 0xEF, 0xF0),
                         hx("AA 09 82 00 24 08 41 00 0B 00 19 00 EF 00 F0 CC 33 C3 3C"))

    def test_bounds(self):
        with self.assertRaises(ValueError):
            D.fill_rect(0, 0, 240, 10)


if __name__ == "__main__":
    unittest.main()
