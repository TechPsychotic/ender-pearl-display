"""A fake printer API with plausible data: mockups on the laptop and tests (no server, no printer)."""
import math
import time

NOW = time.time()


class FakeApi:
    def __init__(self, printing=False, paused=False):
        self.calls, self.printing, self.paused = [], printing, paused
        self.cfg = {}

    def state(self):
        base = {"filament": {"family": "PLA"}, "queue": {"items": []}, "book": {"hours": 31.4}, "sd": None}
        if not self.printing:
            return {**base, "printing": False, "idle_temps": [196.4, 200, 55.1, 55]}
        return {**base, "printing": True, "job": "benchy_pla_0.2mm.gcode",
                "status": {"state": "paused" if self.paused else "printing", "layer": 93, "layers": 200, "z": 18.8,
                           "temps": [199.6, 200, 55.0, 55], "sent": 47000, "total": 100000, "remaining": 4320,
                           "finish_at": NOW + 4320, "updated": NOW, "started": NOW - 2830,
                           "overrides": {"speed": 1.1, "flow": 1.0}, "objects": ["benchy id:0 copy 0", "calicat id:1 copy 0"], "dropped": []}}

    def files(self):
        est = ["1h 19m", "22 min", "3h 05m", "1h 48m", "2h 10m", "35 min", "18 min", "4h 41m", "52 min"]
        return [{"name": n, "mtime": NOW - i * 86400 * 1.7, "kind": "gcode", "estimate": est[i]} for i, n in enumerate(
            ["benchy_pla_0.2mm.gcode", "clearance_test.gcode", "gridfinity_2x3.gcode", "vase_spiral.gcode", "phone_stand.gcode",
             "hinge_pip.gcode", "calibration_cube.gcode", "lithophane_family.gcode", "cable_clip_x8.gcode"])]

    def plan(self, name):
        return {"estimate": "1h 19m", "filament_m": 4.62, "layers": 200, "settings": {"material": "pla_loop"},
                "layer_fan": [0, 0, 0] + [100] * 197}

    def preview(self, name, n, w, h):
        """Paths in a w x h box: a hull outline and an inner wall, the first ~60 % printed."""
        def ring(r, k=48, sx=1.0, sy=0.62):
            return [(round(w / 2 + math.cos(2 * math.pi * i / k) * r * sx * w / 2), round(h / 2 + math.sin(2 * math.pi * i / k) * r * sy * w / 2 * 0.95))
                    for i in range(k + 1)]
        outer, inner = ring(0.92), ring(0.78)
        cut = int(len(outer) * 0.6)
        cabin = [(36, 20), (62, 20), (62, 46), (36, 46), (36, 20)]
        return [(outer[:cut + 1], True), (outer[cut:], False), (inner, False), (cabin, True)]

    def model_preview(self, name, w, h):
        """Top view of the model (a few outlines) in a w x h box."""
        def ring(cx, cy, rx, ry, k=40):
            return [(round(cx + math.cos(2 * math.pi * i / k) * rx), round(cy + math.sin(2 * math.pi * i / k) * ry)) for i in range(k + 1)]
        return [(ring(w * 0.42, h / 2, w * 0.3, h * 0.42), False), (ring(w * 0.42, h / 2, w * 0.24, h * 0.34), False),
                ([(int(w * 0.36), int(h * 0.3)), (int(w * 0.5), int(h * 0.3)), (int(w * 0.5), int(h * 0.62)), (int(w * 0.36), int(h * 0.62)), (int(w * 0.36), int(h * 0.3))], True),
                (ring(w * 0.84, h * 0.55, w * 0.1, h * 0.3, 24), False)]

    def objects_preview(self, name, w, h):
        def ring(cx, cy, rx, ry, k=36):
            return [(round(cx + math.cos(2 * math.pi * i / k) * rx), round(cy + math.sin(2 * math.pi * i / k) * ry)) for i in range(k + 1)]
        return {"objects": [{"name": "benchy id:0 copy 0", "paths": [ring(w * 0.33, h * 0.5, w * 0.24, h * 0.38), ring(w * 0.33, h * 0.5, w * 0.17, h * 0.28)]},
                            {"name": "calicat id:1 copy 0", "paths": [ring(w * 0.78, h * 0.4, w * 0.13, h * 0.2, 6)]},
                            {"name": "clip id:2 copy 0", "paths": [[(int(w * 0.66), int(h * 0.75)), (int(w * 0.92), int(h * 0.75)), (int(w * 0.92), int(h * 0.88)), (int(w * 0.66), int(h * 0.88)), (int(w * 0.66), int(h * 0.75))]]}]}

    def calibrations(self):
        return {"temp": {"label": "Temperature tower", "kind": "tower", "unit": "°C", "defaults": {"PLA": [225, 195, -5], "PETG": [250, 220, -5]},
                         "look_for": "Pick the band with the cleanest surface and least stringing between the towers."},
                "retract": {"label": "Retraction tower", "kind": "tower", "unit": "mm", "defaults": {"PLA": [0.2, 1.4, 0.2], "PETG": [0.4, 2.4, 0.4]},
                            "look_for": "Pick the lowest band with no strings between the towers."},
                "speed": {"label": "Speed / VFA tower", "kind": "tower", "unit": "mm/s", "defaults": {"PLA": [60, 150, 15]}, "look_for": "Waves on the walls."},
                "fan": {"label": "Fan tower", "kind": "tower", "unit": "%", "defaults": {"PLA": [40, 100, 20]}, "look_for": "Bonding and edges."},
                "flow": {"label": "Flow rate pads", "kind": "plate", "unit": "%", "defaults": {"PLA": [90, 110, 5]}, "look_for": "Smoothest top surface."},
                "firstlayer": {"label": "First layer pads", "kind": "plate", "unit": "mm", "defaults": {"PLA": [-0.1, 0.1, 0.05]}, "look_for": "Even, slightly squished lines."},
                "volumetric": {"label": "Max volumetric speed", "kind": "plate", "unit": "mm³/s", "defaults": {"PLA": [8, 16, 2]}, "look_for": "Highest pad without gaps."}}

    def calibrate(self, test, material, start, end, step):
        self.calls.append(("calibrate", test, material, start, end, step))
        return {"name": f"calib_{test}.gcode", "info": {"layers": 140, "estimate": "52 min", "actions": [{"layer": 25, "type": "temp", "value": 220}]}}

    def printer(self, action, timeout=30, **kw):
        self.calls.append(("printer", action, kw))
        if action == "sd_list":
            return {"files": self.sd_list()}
        if action == "mesh":
            return {"grid": [[0.12, 0.05, -0.02, 0.18], [0.04, -0.03, -0.08, 0.09], [-0.01, -0.06, -0.10, 0.05], [0.08, 0.01, -0.04, 0.21]]}
        if action == "settings":
            return {"settings": {"M203": {"X": 500, "Y": 500, "Z": 10, "E": 40}, "M204": {"P": 2500, "T": 2500},
                                 "M92": {"X": 80, "Y": 80, "Z": 400, "E": 424.9}}}
        return {"ok": True}

    def sd_list(self):
        return [{"name": f"F{i}~1.GCO", "long": n, "size": s} for i, (n, s) in enumerate(
            [("bracket.gcode", 1157309), ("bottle_cap.gcode", 5962927), ("card_holder.gcode", 8768064), ("flick_toy.gcode", 48171703)])]

    def queue(self):
        return {"items": [{"name": "cable_clip_x8.gcode", "copies": 3, "done": 1, "status": "queued"}], "waiting": None}

    def queue_op(self, op, **kw):
        self.calls.append(("queue", op, kw)); return {"ok": True}

    def cmd(self, c):
        self.calls.append(("cmd", c)); return {"ok": True}

    def stop(self):
        self.calls.append(("stop",)); return {"ok": True}

    def print_file(self, name, actions=None):
        self.calls.append(("print", name)); return {"ok": True}

    def display_config(self):
        return self.cfg

    def save_display_config(self, cfg):
        self.calls.append(("display_config", cfg)); self.cfg.update(cfg)

    def address(self):
        return "192.168.68.111"

    def pi_info(self):
        return "48°C · up 2d"
