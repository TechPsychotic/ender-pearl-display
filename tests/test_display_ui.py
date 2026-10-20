"""display/ui.py: menus, confirmations and partial redraws, with a fake API and a fake display (no hardware)."""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pi", "display"))
import protocol as D  # noqa: E402
import ui  # noqa: E402


class FakeDisplay:
    port = "/dev/fake"

    def __init__(self):
        self.frames = []

    def send(self, *f):
        self.frames += f


def texts(frames):
    return [p[11:].decode() for c, p in D.parse(b"".join(frames))[0] if c == 0x98]


def wait(app):
    for _ in range(200):
        if not app.busy:
            return
        time.sleep(0.01)


def labels(app):
    return [it.label for it in app.screen.items()]


def go(app, label):
    app.screen.sel = labels(app).index(label)
    app.on_press()


class UI(unittest.TestCase):
    def setUp(self):
        self.api, self.disp = ui.FakeApi(), FakeDisplay()
        self.app = ui.App(self.api, self.disp)
        self.app.refresh()

    def test_status_and_partial_redraw(self):
        self.app.draw(full=True)
        t = texts(self.disp.frames)
        self.assertTrue(any("Nozzle" in x for x in t) and any("Print a file" in x for x in t))
        self.disp.frames.clear()
        self.app.draw()
        self.assertEqual(texts(self.disp.frames), [])           # nothing changed, nothing redrawn
        self.app.on_turn(1)
        self.app.draw()
        self.assertEqual(len(texts(self.disp.frames)), 2)        # only the two rows whose highlight moved

    def test_print_needs_confirmation(self):
        go(self.app, "Print a file")
        for _ in range(100):
            if "demo_cube.gcode" in labels(self.app):
                break
            time.sleep(0.01)
        go(self.app, "demo_cube.gcode")
        self.assertEqual(labels(self.app)[0], "No, go back")      # "No" is selected first
        self.app.on_press()                                       # pressing straight away = No
        self.assertEqual(self.api.calls, [])
        go(self.app, "demo_cube.gcode")
        go(self.app, "Bed is clear: print")
        wait(self.app)
        self.assertEqual(self.api.calls, [("print", "demo_cube.gcode")])
        self.assertEqual(len(self.app.stack), 1)                  # back on the status screen

    def test_printing_menu_and_stop(self):
        self.api.printing = True
        self.app.refresh()
        self.assertEqual(labels(self.app), ["Pause", "Tune", "Stop print", "Info"])
        go(self.app, "Stop print")
        go(self.app, "Yes, stop it")
        wait(self.app)
        self.assertIn(("stop",), self.api.calls)

    def test_tune_value_limits(self):
        self.api.printing = True
        self.app.refresh()
        go(self.app, "Tune")
        go(self.app, "Speed")
        for _ in range(30):
            self.app.on_turn(1)
        self.assertEqual(self.app.screen.v, 150)                  # clamped like run_live (0.5–1.5)
        self.app.on_press()
        wait(self.app)
        self.assertIn(("cmd", "speed 1.5"), self.api.calls)

    def test_dim_and_wake(self):
        self.app.last_input = time.time() - ui.DIM_AFTER - 1
        self.app.tick()
        self.assertTrue(self.app.dimmed)
        sel = self.app.screen.sel
        self.app.on_turn(1)                                       # first touch only wakes
        self.assertEqual(self.app.screen.sel, sel)
        self.assertFalse(self.app.dimmed)

    def test_server_down(self):
        class Down(ui.FakeApi):
            def state(self):
                raise RuntimeError("connection refused")
        app = ui.App(Down(), FakeDisplay()); app.refresh(); app.draw(full=True)
        self.assertTrue(any("Server not reachable" in x for x in texts(app.disp.frames)))


if __name__ == "__main__":
    unittest.main()
