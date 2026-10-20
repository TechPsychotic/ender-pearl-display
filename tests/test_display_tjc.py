"""display/tjc.py: TJC standard instructions (our own display firmware, plan C2)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pi", "display"))
import tjc  # noqa: E402

E = b"\xff\xff\xff"


class Commands(unittest.TestCase):
    def test_drawing(self):
        self.assertEqual(tjc.cls(0), b"cls 0" + E)
        self.assertEqual(tjc.fill(1, 2, 3, 4, 65535), b"fill 1,2,3,4,65535" + E)
        self.assertEqual(tjc.pic(10, 20, 3), b"pic 10,20,3" + E)
        self.assertEqual(tjc.xpic(0, 0, 120, 40, 0, 40, 3), b"xpic 0,0,120,40,0,40,3" + E)
        self.assertEqual(tjc.circle(5, 6, 7, 1, True), b"cirs 5,6,7,1" + E)
        self.assertEqual(tjc.brightness(150), b"dim=100" + E)

    def test_text_is_safe(self):
        c = tjc.text(10, 20, 200, 30, 'say "hi"\n', 1, 0xFFFF, align=tjc.CENTER)
        self.assertEqual(c, b"xstr 10,20,200,30,1,65535,0,1,1,3,\"say 'hi' \"" + E)
        self.assertNotIn(b"\xff", c[:-3])

    def test_replies(self):
        self.assertEqual(tjc.parse_replies(b"\x01" + E + b"\x1e" + E + b"\x01"), [(1, b""), (0x1E, b"")])


if __name__ == "__main__":
    unittest.main()
