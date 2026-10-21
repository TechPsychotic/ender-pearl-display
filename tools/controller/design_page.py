"""The Design tab: build a screen for the printer's display from what's flashed in it, without code.

Left: the screen (drag elements to move them, drag the corner handle to resize, arrow keys nudge, Delete removes).
Middle: the elements, bottom to top (later ones cover earlier ones). Right: the selected element's settings and
warnings (text that won't fit, characters the font doesn't have). "Live on the printer" redraws the real display after
every change, through the bench (the Ender Pearl screen is paused meanwhile)."""
import copy
import json
import os

from gi.repository import Adw, Gdk, Gio, GLib, Gtk
from PIL import ImageDraw

import designer as D
import mirror

SCALE = 2
DESIGNS = os.path.join(os.path.expanduser("~"), ".config", "ender-pearl-controller", "designs")
HANDLE = 8   # px (screen) of the resize handle


def rgba(c):
    r = Gdk.RGBA()
    r.red, r.green, r.blue, r.alpha = c[0] / 255, c[1] / 255, c[2] / 255, 1.0
    return r


def from_rgba(r):
    return [round(r.red * 255), round(r.green * 255), round(r.blue * 255)]


class DesignPage(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.win = win
        self.mirror = mirror.Mirror(D.LocalAssets(win.pi))
        self.design = copy.deepcopy(D.templates()["Header and card"])
        self.sel = None
        self.undo, self.redo = [], []
        self.path = None
        self.live = False
        self.inflight = False
        self.pending = False
        self.batch_id = 0
        self._building = False
        self._drag = None
        self._push_tid = None
        self.ctx = {"data": None, "paths": {}}
        self.files, self.layers, self._fetching = [], {}, set()

        self.append(self._toolbar())
        body = Gtk.Box(spacing=16, margin_top=10, margin_bottom=14, margin_start=18, margin_end=18, vexpand=True)
        body.append(self._screen())
        body.append(self._layers())
        self.props_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        sc = Gtk.ScrolledWindow(child=self.props_box, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        sc.set_size_request(330, -1)
        body.append(sc)
        self.append(body)
        self.refresh(rebuild=True)

    # ================================================================ widgets
    def _toolbar(self):
        bar = Gtk.Box(spacing=6, margin_top=10, margin_start=18, margin_end=18)
        tmpl = Gtk.MenuButton(label="Templates", tooltip_text="Start from a ready screen")
        menu = Gio.Menu()
        for name in D.templates():
            menu.append(name, f"design.template::{name}")
        tmpl.set_menu_model(menu)
        bar.append(tmpl)
        ag = Gio.SimpleActionGroup()
        a = Gio.SimpleAction.new("template", GLib.VariantType.new("s"))
        a.connect("activate", lambda _a, v: self.load_template(v.get_string()))
        ag.add_action(a)
        a = Gio.SimpleAction.new("add", GLib.VariantType.new("s"))
        a.connect("activate", lambda _a, v: self.add(v.get_string()))
        ag.add_action(a)
        self.insert_action_group("design", ag)
        for icon, tip, fn in (("document-open-symbolic", "Open a design", self.open), ("document-save-symbolic", "Save the design", self.save),
                              ("edit-undo-symbolic", "Undo (Ctrl+Z)", self.do_undo), ("edit-redo-symbolic", "Redo (Ctrl+Shift+Z)", self.do_redo)):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.connect("clicked", lambda *_a, f=fn: f())
            bar.append(b)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        bar.append(Gtk.Label(label="Wallpaper", css_classes=["dim-label"]))
        self.walls = list(D.MANIFEST["wallpapers"])
        self.wall_dd = Gtk.DropDown.new_from_strings([w.replace("-", " ").title() for w in self.walls])
        self.wall_dd.connect("notify::selected", lambda *_: self._set_wall())
        bar.append(self.wall_dd)
        bar.append(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL))
        b = Gtk.Button(label="What can the display do?")
        b.connect("clicked", lambda *_: self.show_capabilities())
        bar.append(b)
        b = Gtk.Button(label="Commands")
        b.set_tooltip_text("The TJC instructions this screen sends, and the same screen as Python for the Pi app")
        b.connect("clicked", lambda *_: self.show_commands())
        bar.append(b)
        spacer = Gtk.Box(hexpand=True)
        bar.append(spacer)
        self.live_note = Gtk.Label(label="", css_classes=["dim-label", "caption"])
        bar.append(self.live_note)
        bar.append(Gtk.Label(label="Live on the printer"))
        self.live_sw = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Redraw the real display after every change "
                                  "(pauses the Ender Pearl screen; switch off to bring it back)")
        self.live_sw.connect("notify::active", lambda sw, _p: self._live_toggled(sw.get_active()))
        bar.append(self.live_sw)
        return bar

    def _screen(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.pic = Gtk.Picture(can_shrink=False, content_fit=Gtk.ContentFit.FILL)
        self.pic.set_size_request(240 * SCALE, 320 * SCALE)
        frame = Gtk.Frame(child=self.pic, css_classes=["card"], valign=Gtk.Align.START)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self._drag_begin)
        drag.connect("drag-update", self._drag_update)
        drag.connect("drag-end", lambda *_: self._drag_end())
        self.pic.add_controller(drag)
        box.append(frame)
        self.pos_note = Gtk.Label(label="", css_classes=["dim-label", "caption"])
        box.append(self.pos_note)
        box.append(Gtk.Label(label="Drag to move · corner handle resizes · arrows nudge (Shift: 10 px) · Delete removes",
                             css_classes=["dim-label", "caption"], wrap=True, max_width_chars=60))
        return box

    def _layers(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_size_request(250, -1)
        head = Gtk.Box(spacing=6)
        head.append(Gtk.Label(label="Elements", css_classes=["heading"], xalign=0, hexpand=True))
        add = Gtk.MenuButton(icon_name="list-add-symbolic", tooltip_text="Add an element", css_classes=["suggested-action"])
        menu = Gio.Menu()
        for k, (title, _d) in D.KINDS.items():
            menu.append(title, f"design.add::{k}")
        add.set_menu_model(menu)
        head.append(add)
        box.append(head)
        self.list = Gtk.ListBox(css_classes=["boxed-list"], selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.connect("row-selected", self._row_selected)
        sc = Gtk.ScrolledWindow(child=self.list, vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        box.append(sc)
        row = Gtk.Box(spacing=6, homogeneous=True)
        for icon, tip, fn in (("go-up-symbolic", "Bring forward (drawn later)", lambda: self.move(1)),
                              ("go-down-symbolic", "Send backward (drawn earlier)", lambda: self.move(-1)),
                              ("edit-copy-symbolic", "Duplicate", self.duplicate), ("user-trash-symbolic", "Delete", self.delete)):
            b = Gtk.Button(icon_name=icon, tooltip_text=tip)
            b.connect("clicked", lambda *_a, f=fn: f())
            row.append(b)
        box.append(row)
        box.append(Gtk.Label(label="Top of the list = drawn last = on top.", css_classes=["dim-label", "caption"], xalign=0))
        return box

    # ================================================================ model changes
    def snapshot(self):
        self.undo.append(json.dumps(self.design))
        if len(self.undo) > 200:
            self.undo.pop(0)
        self.redo.clear()

    def do_undo(self):
        if self.undo:
            self.redo.append(json.dumps(self.design))
            self.design = json.loads(self.undo.pop())
            self.sel = None
            self.refresh(rebuild=True)

    def do_redo(self):
        if self.redo:
            self.undo.append(json.dumps(self.design))
            self.design = json.loads(self.redo.pop())
            self.sel = None
            self.refresh(rebuild=True)

    @property
    def els(self):
        return self.design.setdefault("elements", [])

    def add(self, kind):
        self.snapshot()
        e = D.new(kind)
        if kind == "picture":
            e["w"], e["h"] = D.picture_size(e["picture"])
        self.els.append(e)
        self.sel = len(self.els) - 1
        self.refresh(rebuild=True)

    def delete(self):
        if self.sel is not None:
            self.snapshot()
            self.els.pop(self.sel)
            self.sel = min(self.sel, len(self.els) - 1) if self.els else None
            self.refresh(rebuild=True)

    def duplicate(self):
        if self.sel is not None:
            self.snapshot()
            e = copy.deepcopy(self.els[self.sel])
            e["x"] += 8
            e["y"] += 8
            self.els.insert(self.sel + 1, e)
            self.sel += 1
            self.refresh(rebuild=True)

    def move(self, d):
        i = self.sel
        if i is None or not 0 <= i + d < len(self.els):
            return
        self.snapshot()
        self.els[i], self.els[i + d] = self.els[i + d], self.els[i]
        self.sel = i + d
        self.refresh(rebuild=True)

    def nudge(self, dx, dy):
        if self.sel is None:
            return False
        self.snapshot()
        e = self.els[self.sel]
        e["x"] += dx
        e["y"] += dy
        self.refresh(props=True)
        return True

    def set_prop(self, key, value, rebuild_props=False, from_panel=True):
        if self._building or self.sel is None:
            return
        e = self.els[self.sel]
        if e.get(key) == value:
            return
        self.snapshot()
        e[key] = value
        if key == "picture":
            e["w"], e["h"] = D.picture_size(value)
            rebuild_props = True
        self.refresh(props=rebuild_props or not from_panel, labels=True)

    def _set_wall(self):
        if self._building:
            return
        w = self.walls[self.wall_dd.get_selected()]
        if w != self.design.get("wallpaper"):
            self.snapshot()
            self.design["wallpaper"] = w
            self.refresh()

    def load_template(self, name):
        self.snapshot()
        self.design = copy.deepcopy(D.templates()[name])
        self.sel = None
        self.path = None
        self.refresh(rebuild=True)

    # ================================================================ drawing
    def refresh(self, rebuild=False, props=False, labels=False):
        """Redraw the preview; rebuild the element list / settings when needed; send to the printer when live."""
        self.ensure_paths()
        img = self.mirror.render(D.frame(self.design, self.ctx)).resize((240 * SCALE, 320 * SCALE), 0)
        if self.sel is not None and self.sel < len(self.els):
            x, y, w, h = D.bbox(self.els[self.sel])
            d = ImageDraw.Draw(img)
            box = (x * SCALE - 1, y * SCALE - 1, (x + w) * SCALE, (y + h) * SCALE)
            d.rectangle(box, outline=(255, 64, 200), width=2)
            if self.els[self.sel]["type"] != "line":
                d.rectangle((box[2] - HANDLE, box[3] - HANDLE, box[2] + 2, box[3] + 2), fill=(255, 64, 200))
            e = self.els[self.sel]
            self.pos_note.set_label(f"{D.KINDS[e['type']][0]}: x {e['x']}, y {e['y']}, {e['w']} × {e['h']}")
        else:
            self.pos_note.set_label("Click an element to select it")
        data = img.tobytes()
        self.pic.set_paintable(Gdk.MemoryTexture.new(img.width, img.height, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(data), img.width * 3))
        if rebuild:
            self._building = True
            if self.design.get("wallpaper") in self.walls:
                self.wall_dd.set_selected(self.walls.index(self.design["wallpaper"]))
            self._building = False
            self._fill_list()
        elif labels:
            self._relabel()
        if rebuild or props:
            self._fill_props()
        else:
            self._show_warnings()
        self.schedule_push()

    def _title(self, e):
        t = D.KINDS[e["type"]][0]
        if e["type"] == "text":
            return f"{t} · “{e['text'][:22]}”"
        if e["type"] == "icon":
            return f"{t} · {e['icon']}"
        if e["type"] == "panel":
            return f"{t}{' (focused)' if e['style'] == 'focus' else ''}"
        if e["type"] == "picture":
            return f"{t} · {e['picture']}"
        if e["type"] == "preview":
            return f"{t} · {D.VIEWS[e['view']].split(',')[0]}"
        if e["type"] == "ctext":
            return f"{t} · “{e['text'][:16]}”"
        if e["type"] == "cimage":
            return f"{t} · {os.path.basename(e['image_file']) or 'no file'}"
        return t

    def _fill_list(self):
        self._building = True
        while (r := self.list.get_row_at_index(0)) is not None:
            self.list.remove(r)
        for i in range(len(self.els) - 1, -1, -1):   # topmost first
            e = self.els[i]
            row = Adw.ActionRow(title=GLib.markup_escape_text(self._title(e)), subtitle=f"{e['x']}, {e['y']} · {e['w']} × {e['h']}")
            ws = D.warnings(e, self.design, self.ctx)
            if ws:
                row.add_suffix(Gtk.Image(icon_name="dialog-warning-symbolic", tooltip_text="\n".join(ws)))
            row.idx = i
            self.list.append(row)
            if i == self.sel:
                self.list.select_row(row)
        self.list.set_placeholder(Gtk.Label(label="No elements yet: add one with +", css_classes=["dim-label"], margin_top=20))
        self._building = False

    def _relabel(self):
        i = 0
        while (row := self.list.get_row_at_index(i)) is not None:
            e = self.els[row.idx]
            row.set_title(GLib.markup_escape_text(self._title(e)))
            row.set_subtitle(f"{e['x']}, {e['y']} · {e['w']} × {e['h']}")
            i += 1

    def _row_selected(self, _l, row):
        if self._building:
            return
        self.sel = row.idx if row else None
        self.refresh(props=True)

    # ================================================================ settings of the selected element
    def _fill_props(self):
        try:
            self._fill_props_inner()
        finally:
            self._building = False

    def _fill_props_inner(self):
        self._building = True
        while (c := self.props_box.get_first_child()) is not None:
            self.props_box.remove(c)
        if self.sel is None or self.sel >= len(self.els):
            g = Adw.PreferencesGroup(title="Nothing selected", description="Pick an element in the list or on the screen, "
                                     "or add one with +. Not sure what's possible? Try a template, or “What can the display do?”.")
            self.props_box.append(g)
            self._building = False
            return
        e = self.els[self.sel]
        k = e["type"]
        g = Adw.PreferencesGroup(title=D.KINDS[k][0])
        names = (("x", "X", -240, 480), ("y", "Y", -320, 640)) + ((("w", "Δ X (length)", -240, 240), ("h", "Δ Y", -320, 320)) if k == "line" else
                                                                (("w", "Width", 1, 240), ("h", "Height", 1, 320)))
        for key, title, lo, hi in names:
            r = Adw.SpinRow.new_with_range(lo, hi, 1)
            r.set_title(title)
            r.set_value(e[key])
            r.connect("notify::value", lambda row, _p, key=key: self.set_prop(key, int(row.get_value())))
            g.add(r)
        self.props_box.append(g)

        g = Adw.PreferencesGroup(title="Look")
        if k == "panel":
            g.add(self._combo("Style", ["glass", "focus"], ["Glass", "Focused (lighter, teal edge)"], "style"))
            g.add(self._switch("Highlight line on top", "edge"))
        if k in ("text", "ctext"):
            r = Adw.EntryRow(title="Text  ·  {field} = live data", text=e["text"])
            r.connect("changed", lambda row: self.set_prop("text", row.get_text()))
            g.add(r)
            g.add(self._insert_data(r))
        if k == "text":
            g.add(self._combo("Font", D.FONT_ROLES, [D.FONT_TITLES[f] for f in D.FONT_ROLES], "font"))
        if k == "ctext":
            g.add(self._font_row())
            g.add(self._spin("Size (px)", "size", 6, 200))
            g.add(self._combo("Edges", [1, 2, 3, 4], ["Sharp (fewest commands)", "Smooth ×2", "Smooth ×3", "Smoothest"], "smooth"))
        if k == "icon":
            g.add(self._combo("Icon", D.ICON_NAMES, D.ICON_NAMES, "icon"))
            g.add(self._combo("Size", ["icon", "icon_s"], ["24 px", "18 px"], "size"))
        if k == "picture":
            pics = [p for p in D.MANIFEST["pictures"] if not p.endswith(("_bg.png", "_glass.png", "_focus.png"))]
            g.add(self._combo("Picture", pics, pics, "picture"))
        if k == "cimage":
            g.add(self._file_row("Image", "image_file", "Images", ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp", "*.gif"]))
            g.add(self._spin("Colours", "colors", 2, 64))
        if k == "preview":
            self._preview_rows(g, e)
        if k in ("text", "ctext", "icon", "bar", "rect", "line", "circle"):
            g.add(self._color("Colour" if k != "bar" else "Filled part", "color"))
        if k == "bar":
            g.add(self._color("Empty part", "track"))
            g.add(self._combo("Value from", list(D.BAR_SOURCES), list(D.BAR_SOURCES.values()), "source", rebuild=True))
            if e.get("source", "fixed") == "fixed":
                g.add(self._spin("Value (%)", "value", 0, 100))
        if k in D.ROUNDED:
            g.add(self._spin("Corner radius", "radius", 0, 60))
        if k in ("text", "ctext"):
            g.add(self._combo("Horizontal", D.ALIGN, ["Left", "Centre", "Right"], "align"))
        if k == "text":
            g.add(self._combo("Vertical", D.VALIGN, ["Top", "Middle", "Bottom"], "valign"))
        if k in ("text", "ctext", "icon"):
            g.add(self._combo("Behind it", D.UNDER, [D.UNDER_TITLES[u] for u in D.UNDER], "under", rebuild=True))
            if e.get("under") == "solid":
                g.add(self._color("Solid colour", "solid"))
        if k == "circle":
            g.add(self._switch("Filled", "filled"))
        self.props_box.append(g)
        self.warn_group = Adw.PreferencesGroup(title="Check")
        self.props_box.append(self.warn_group)
        self.warn_rows = []
        self._building = False
        self._show_warnings()

    def _spin(self, title, key, lo, hi):
        r = Adw.SpinRow.new_with_range(lo, hi, 1)
        r.set_title(title)
        r.set_value(self.els[self.sel].get(key, lo))
        r.connect("notify::value", lambda row, _p: self.set_prop(key, int(row.get_value())))
        return r

    def _insert_data(self, entry):
        """A drop-down that inserts a {field} into the text (live printer data)."""
        r = Adw.ActionRow(title="Insert live data", subtitle="Filled in from the printer (sample values when not connected)")
        names = list(D.DATA_FIELDS)
        dd = Gtk.DropDown.new_from_strings(["Choose…"] + [f"{D.DATA_FIELDS[n]}  {{{n}}}" for n in names])
        dd.set_valign(Gtk.Align.CENTER)

        def pick(d, _p):
            i = d.get_selected()
            if i > 0:
                entry.set_text(entry.get_text() + "{" + names[i - 1] + "}")
                d.set_selected(0)
        dd.connect("notify::selected", pick)
        r.add_suffix(dd)
        return r

    def _file_row(self, title, key, kind, patterns):
        e = self.els[self.sel]
        r = Adw.ActionRow(title=title, subtitle=os.path.basename(e.get(key) or "") or "none chosen")
        b = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)

        def choose(*_a):
            d = Gtk.FileDialog(title=f"Choose {title.lower()}")
            f = Gtk.FileFilter(name=kind)
            for pt in patterns:
                f.add_pattern(pt)
            store = Gio.ListStore.new(Gtk.FileFilter)
            store.append(f)
            d.set_filters(store)

            def done(dlg, res):
                try:
                    self.set_prop(key, dlg.open_finish(res).get_path(), rebuild_props=True)
                except GLib.Error:
                    pass
            d.open(self.win, None, done)
        b.connect("clicked", choose)
        r.add_suffix(b)
        return r

    def _font_row(self):
        """Any font installed on this computer (searchable), or a font file."""
        fonts = self._system_fonts()
        e = self.els[self.sel]
        r = Adw.ActionRow(title="Font", subtitle=os.path.basename(e.get("font_file") or "") or "Pillow's default")
        labels = [n for n, _ in fonts]
        dd = Gtk.DropDown.new_from_strings(["Installed fonts…"] + labels)
        dd.set_enable_search(True)
        dd.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        dd.set_valign(Gtk.Align.CENTER)

        def pick(d, _p):
            i = d.get_selected()
            if i > 0:
                self.set_prop("font_file", fonts[i - 1][1], rebuild_props=True)
        dd.connect("notify::selected", pick)
        r.add_suffix(dd)
        b = Gtk.Button(icon_name="document-open-symbolic", tooltip_text="A font file (.ttf / .otf)", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda *_a: self._choose_font_file())
        r.add_suffix(b)
        return r

    def _choose_font_file(self):
        d = Gtk.FileDialog(title="Choose a font file")
        f = Gtk.FileFilter(name="Fonts")
        for pt in ("*.ttf", "*.otf", "*.ttc"):
            f.add_pattern(pt)
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        d.set_filters(store)

        def done(dlg, res):
            try:
                self.set_prop("font_file", dlg.open_finish(res).get_path(), rebuild_props=True)
            except GLib.Error:
                pass
        d.open(self.win, None, done)

    def _system_fonts(self):
        if getattr(self, "_fonts", None) is None:
            import subprocess
            out = subprocess.run(["fc-list", ":", "family", "style", "file"], capture_output=True, text=True).stdout
            seen = {}
            for line in out.splitlines():
                path, _, rest = line.partition(": ")
                if not path.lower().endswith((".ttf", ".otf")):
                    continue
                fam = rest.split(":")[0].split(",")[0]
                sty = rest.split("style=")[1].split(",")[0] if "style=" in rest else ""
                seen.setdefault(f"{fam} {sty}".strip(), path)
            self._fonts = sorted(seen.items())
        return self._fonts

    def _preview_rows(self, g, e):
        files = ["", *self.files]
        r = Adw.ComboRow(title="G-code file", model=Gtk.StringList.new(["The current print"] + self.files))
        if e.get("file", "") in files:
            r.set_selected(files.index(e.get("file", "")))
        r.connect("notify::selected", lambda row, _p: self.set_prop("file", files[row.get_selected()]))
        g.add(r)
        g.add(self._combo("View", list(D.VIEWS), list(D.VIEWS.values()), "view", rebuild=True))
        if e["view"] == "layers":
            sw = Adw.SwitchRow(title="Follow the print's current layer", active=int(e.get("layer", -1)) < 0)
            sw.connect("notify::active", lambda row, _p: self.set_prop("layer", -1 if row.get_active() else 0, rebuild_props=True))
            g.add(sw)
            if int(e.get("layer", -1)) >= 0:
                hi = self.layer_count(e)
                sc = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, max(1, hi - 1), 1)
                sc.set_value(e["layer"])
                sc.set_hexpand(True)
                sc.set_draw_value(True)
                sc.set_digits(0)
                sc.connect("value-changed", lambda w: self._debounced_layer(int(w.get_value())))
                lr = Adw.ActionRow(title="Layer", subtitle=f"of {hi}" if hi else "")
                lr.add_suffix(sc)
                g.add(lr)
            g.add(self._color("Printed", "done"))
            g.add(self._color("Still to print", "todo"))
        if e["view"] == "plate":
            g.add(self._switch("Shade by height (darker low, brighter high)", "shade"))
            if not e.get("shade"):
                g.add(self._color("Colour", "done"))
        if e["view"] == "objects":
            g.add(self._color("Outline colour", "done"))
        g.add(Adw.ActionRow(title="How it works", subtitle="The Pi builds these from the G-code (walls of every layer, "
                            "turned into an isometric view) and caches them; here they're scaled into the box and drawn as lines."))

    def _debounced_layer(self, n):
        if getattr(self, "_layer_tid", None):
            GLib.source_remove(self._layer_tid)

        def fire():
            self._layer_tid = None
            self.set_prop("layer", n)
            return False
        self._layer_tid = GLib.timeout_add(120, fire)

    def layer_count(self, e):
        f = e.get("file") or (self.ctx.get("data") or {}).get("_job")
        return self.layers.get(f, 0)

    def _combo(self, title, values, labels, key, rebuild=False):
        r = Adw.ComboRow(title=title, model=Gtk.StringList.new(labels))
        e = self.els[self.sel]
        if e.get(key) in values:
            r.set_selected(values.index(e[key]))
        r.connect("notify::selected", lambda row, _p: self.set_prop(key, values[row.get_selected()], rebuild_props=rebuild))
        return r

    def _switch(self, title, key):
        r = Adw.SwitchRow(title=title, active=bool(self.els[self.sel].get(key)))
        r.connect("notify::active", lambda row, _p: self.set_prop(key, row.get_active()))
        return r

    def _color(self, title, key):
        r = Adw.ActionRow(title=title)
        presets = Gtk.DropDown.new_from_strings(["Preset…"] + list(D.COLORS))
        presets.set_valign(Gtk.Align.CENTER)
        btn = Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(with_alpha=False), valign=Gtk.Align.CENTER)
        btn.set_rgba(rgba(self.els[self.sel][key]))

        def preset(dd, _p):
            if dd.get_selected() > 0:
                c = list(D.COLORS.values())[dd.get_selected() - 1]
                btn.set_rgba(rgba(c))
                dd.set_selected(0)
        presets.connect("notify::selected", preset)
        btn.connect("notify::rgba", lambda b, _p: self.set_prop(key, from_rgba(b.get_rgba())))
        r.add_suffix(presets)
        r.add_suffix(btn)
        r.set_subtitle("The display has 65,536 colours: very close shades look the same")
        return r

    def _show_warnings(self):
        if self.sel is None or self.sel >= len(self.els) or not hasattr(self, "warn_group"):
            return
        for r in self.warn_rows:
            self.warn_group.remove(r)
        ws = D.warnings(self.els[self.sel], self.design, self.ctx)
        cmds = D.element_commands(self.design, self.sel, self.ctx)
        cost = Adw.ActionRow(title=f"{len(cmds)} drawing command{'s' if len(cmds) != 1 else ''}",
                             subtitle=f"about {D.estimate_ms(cmds):.0f} ms on the display")
        self.warn_rows = [Adw.ActionRow(title=GLib.markup_escape_text(w), css_classes=["warning"]) for w in ws] or \
                         [Adw.ActionRow(title="Looks fine on the display", subtitle="Nothing gets cut or wrapped")]
        self.warn_rows.append(cost)
        for r in self.warn_rows:
            self.warn_group.add(r)

    # ================================================================ mouse and keys
    def _drag_begin(self, _g, x, y):
        sx, sy = x / SCALE, y / SCALE
        if self.sel is not None and self.sel < len(self.els) and self.els[self.sel]["type"] != "line":
            bx, by, bw, bh = D.bbox(self.els[self.sel])
            if abs(sx - (bx + bw)) * SCALE <= HANDLE + 3 and abs(sy - (by + bh)) * SCALE <= HANDLE + 3:
                e = self.els[self.sel]
                self.snapshot()
                self._drag = ("size", e["w"], e["h"])
                return
        i = D.hit(self.design, sx, sy)
        if i != self.sel:
            self.sel = i
            self.refresh(rebuild=True)
        if i is not None:
            e = self.els[i]
            self.snapshot()
            self._drag = ("move", e["x"], e["y"])
        else:
            self._drag = None

    def _drag_update(self, _g, dx, dy):
        if not self._drag or self.sel is None:
            return
        e = self.els[self.sel]
        kind, a, b = self._drag
        if kind == "move":
            e["x"], e["y"] = a + round(dx / SCALE), b + round(dy / SCALE)
        else:
            e["w"], e["h"] = max(1, a + round(dx / SCALE)), max(1, b + round(dy / SCALE))
        if not getattr(self, "_drawing", False):   # coalesce: one redraw per frame
            self._drawing = True

            def draw():
                self._drawing = False
                self.refresh(labels=True)
                return False
            GLib.idle_add(draw)

    def _drag_end(self):
        if self._drag:
            self._drag = None
            self.refresh(props=True, labels=True)

    def key(self, keyval, state):
        k = Gdk.keyval_name(keyval)
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        step = 10 if state & Gdk.ModifierType.SHIFT_MASK else 1
        if ctrl and k in ("z", "Z"):
            (self.do_redo if state & Gdk.ModifierType.SHIFT_MASK else self.do_undo)()
            return True
        if ctrl and k in ("d", "D"):
            self.duplicate()
            return True
        moves = {"Left": (-step, 0), "Right": (step, 0), "Up": (0, -step), "Down": (0, step)}
        if k in moves:
            return self.nudge(*moves[k])
        if k == "Delete":
            self.delete()
            return True
        return False

    # ================================================================ live on the printer
    def _sw(self, on):
        self._sw_quiet = True
        self.live_sw.set_active(on)
        self._sw_quiet = False

    def _live_toggled(self, on):
        if getattr(self, "_sw_quiet", False):
            return
        if on and not self.live:
            if not self.win.need(idle=True):
                self._sw(False)
                return

            def ready():
                self.live = True
                self.live_note.set_label("live")
                self.push_now()

            def go():
                if self.win.bench:
                    ready()
                else:
                    self.win.start_bench(then=ready, fail=lambda: self._sw(False))
            if self.win.bench:
                go()
            else:
                self.win.confirm("Show the design on the printer?", "The Ender Pearl screen pauses while you design live; "
                                 "switching Live off (or closing the app) brings it back.", "Go live", go,
                                 destructive=False, cancel=lambda: self._sw(False))
        elif not on and self.live:
            self.live = False
            self.live_note.set_label("")
            if self.win.bench:
                self.win.stop_bench()

    def live_off(self):
        """The bench stopped elsewhere (Bench tab)."""
        if self.live:
            self.live = False
            self._sw(False)
            self.live_note.set_label("")

    def schedule_push(self):
        if not self.live:
            return
        if self._push_tid:
            GLib.source_remove(self._push_tid)
        self._push_tid = GLib.timeout_add(60, lambda: (setattr(self, "_push_tid", None), self.push_now(), False)[2])

    def push_now(self):
        if not self.live or not self.win.bench:
            return
        if self.inflight:
            self.pending = True
            return
        self.inflight, self.pending = True, False
        self.batch_id += 1
        cmds = D.commands(self.design, self.ctx)
        if cmds == getattr(self, "_last_pushed", None) and not getattr(self, "_force", False):
            self.inflight = False
            return
        self._last_pushed = cmds
        try:
            self.win.bench.stdin.write(json.dumps({"batch": cmds, "id": self.batch_id}) + "\n")
            self.win.bench.stdin.flush()
        except (OSError, ValueError) as e:
            self.inflight = False
            self.win.toast(f"live: {e}")

    def batch_done(self, m):
        self.inflight = False
        errs = m.get("errors") or []
        self.live_note.set_label(f"on the display · {m.get('batch')} commands in {m.get('ms')} ms" +
                                 (f" · {len(errs)} error(s): {errs[0].get('name')}" if errs else ""))
        if self.pending:
            self.push_now()

    # ================================================================ files and dialogs
    def save(self):
        os.makedirs(DESIGNS, exist_ok=True)
        d = Gtk.FileDialog(title="Save the design", initial_name=os.path.basename(self.path) if self.path else "my-screen.json")
        d.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self.path) if self.path else DESIGNS))

        def done(dlg, res):
            try:
                self.path = dlg.save_finish(res).get_path()
            except GLib.Error:
                return
            with open(self.path, "w") as f:
                json.dump({"format": "ender-pearl-design", "version": 1, **self.design}, f, indent=1)
            self.win.toast(f"Saved {os.path.basename(self.path)}")
        d.save(self.win, None, done)

    def open(self):
        os.makedirs(DESIGNS, exist_ok=True)
        d = Gtk.FileDialog(title="Open a design")
        d.set_initial_folder(Gio.File.new_for_path(DESIGNS))

        def done(dlg, res):
            try:
                path = dlg.open_finish(res).get_path()
                with open(path) as f:
                    data = json.load(f)
                assert isinstance(data.get("elements"), list)
            except (GLib.Error, OSError, ValueError, AssertionError) as e:
                if not isinstance(e, GLib.Error):
                    self.win.toast(f"Not a design file: {e}")
                return
            self.snapshot()
            self.design = {"wallpaper": data.get("wallpaper", self.walls[0]),
                           "elements": [{**D.new(e["type"]), **e} for e in data["elements"] if e.get("type") in D.KINDS]}
            self.path, self.sel = path, None
            self.refresh(rebuild=True)
        d.open(self.win, None, done)

    def set_state(self, st):
        """Printer state from the window's poll: live data for {fields}, bars and 'follow the print' previews."""
        data = D.data_from_state(st)
        old = self.ctx.get("data")
        self.ctx["data"] = data
        if not self.files and not getattr(self, "_files_asked", False):
            self._files_asked = True
            self.win_bg(lambda: self.win.pi.api("GET", "/api/display/files")["files"], self._got_files)
        uses = any(e["type"] in ("text", "ctext") and "{" in str(e["text"]) or e["type"] == "bar" and e.get("source", "fixed") != "fixed"
                   or e["type"] == "preview" for e in self.els)
        if uses and (old is None or {k: v for k, v in old.items() if k != "clock"} != {k: v for k, v in data.items() if k != "clock"}
                     or old.get("clock") != data.get("clock")):
            self.refresh(labels=True)

    def _got_files(self, files):
        self.files = [f["name"] for f in files]
        if self.sel is not None and self.sel < len(self.els) and self.els[self.sel]["type"] == "preview":
            self.refresh(props=True)

    def win_bg(self, fn, done):
        import threading

        def run():
            try:
                r = fn()
            except Exception as e:   # noqa: BLE001
                GLib.idle_add(self.win.toast, str(e))
                return
            GLib.idle_add(done, r)
        threading.Thread(target=run, daemon=True).start()

    def ensure_paths(self):
        """Fetch the pre-built preview paths the preview elements need (once each)."""
        if not self.win.connected:
            return
        for e in self.els:
            if e["type"] != "preview":
                continue
            key = D.preview_key(e, self.ctx.get("data"))
            view, f, layer = key
            if not f or key in self.ctx["paths"] or key in self._fetching:
                continue
            self._fetching.add(key)
            q = "name=" + GLib.uri_escape_string(f, None, False)
            path = {"plate": f"/api/display/model?{q}&w=204&h=88", "objects": f"/api/display/objects?{q}&w=204&h=150",
                    "layers": f"/api/display/preview?{q}&n={max(0, layer)}&w=98&h=70"}[view]

            def got(r, key=key, f=f):
                self._fetching.discard(key)
                self.ctx["paths"][key] = r.get("objects") if key[0] == "objects" else r.get("paths")
                if f not in self.layers:
                    self.win_bg(lambda: self.win.pi.api("GET", "/api/plan?name=" + GLib.uri_escape_string(f, None, False), timeout=60),
                                lambda plan: (self.layers.__setitem__(f, int(plan.get("layers") or 0)), self.refresh(props=True)))
                self.refresh(labels=True)
            self.win_bg(lambda path=path: self.win.pi.api("GET", path, timeout=60), got)

    def show_commands(self):
        cmds = D.commands(self.design, self.ctx)
        tjc, py = "\n".join(cmds), D.python_code(self.design)
        stack = Adw.ViewStack()
        for name, title, text in (("tjc", f"TJC instructions ({len(cmds)})", tjc), ("py", "Python for the Pi app", py)):
            tv = Gtk.TextView(editable=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=8, left_margin=8)
            tv.get_buffer().set_text(text)
            stack.add_titled(Gtk.ScrolledWindow(child=tv, min_content_height=360, min_content_width=620), name, title)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.append(Adw.ViewSwitcher(stack=stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        box.append(stack)
        d = Adw.AlertDialog(heading="What this screen sends", body="Each line ends with FF FF FF on the wire. The display "
                            "executes them in order; the Python is the same screen as calls on the Pi app's canvas.")
        d.set_extra_child(box)
        d.add_response("close", "Close")
        d.add_response("copy", "Copy shown")
        d.connect("response", lambda _d, r: Gdk.Display.get_default().get_clipboard().set(tjc if stack.get_visible_child_name() == "tjc" else py)
                  if r == "copy" else None)
        d.present(self.win)

    def show_capabilities(self):
        cap = D.capabilities()
        outer = Gtk.Box(spacing=18)
        pic = Gtk.Picture(paintable=self._icon_sheet(), can_shrink=False, valign=Gtk.Align.START)
        outer.append(pic)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        for k, v in cap.items():
            box.append(Gtk.Label(label=f"<b>{GLib.markup_escape_text(k)}</b>\n{GLib.markup_escape_text(v)}", use_markup=True,
                                 wrap=True, xalign=0, max_width_chars=48))
        outer.append(Gtk.ScrolledWindow(child=box, hexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER, min_content_height=480))
        sc = Gtk.ScrolledWindow(child=outer, min_content_height=480, min_content_width=860, vscrollbar_policy=Gtk.PolicyType.NEVER)
        d = Adw.AlertDialog(heading="What the display can do", body="Everything below is already in the flashed firmware: "
                            "you can use it in a design without building a new one.")
        d.set_extra_child(sc)
        d.add_response("close", "Close")
        d.present(self.win)

    def _icon_sheet(self):
        """Every icon and font, drawn by the display's own code (rendered here)."""
        els, cols = [], 9
        for i, name in enumerate(D.ICON_NAMES):
            x, y = 6 + (i % cols) * 26, 6 + (i // cols) * 26
            els.append(D.new("icon", x=x, y=y, w=24, h=24, icon=name, under="bg"))
        y = 6 + ((len(D.ICON_NAMES) + cols - 1) // cols) * 26 + 6
        for f in ("small", "label", "body", "value"):
            hgt = D.T.FONTS[f][0] + 4
            els.append(D.new("text", x=6, y=y, w=228, h=hgt, text=f"{f} {D.T.FONTS[f][0]}px Aa 0123", font=f, under="bg"))
            y += hgt
        els.append(D.new("text", x=6, y=y, w=228, h=68, text="64%", font="big", under="bg"))
        img = self.mirror.render(D.frame({"wallpaper": self.design.get("wallpaper"), "elements": els})).resize((360, 480), 0)
        return Gdk.MemoryTexture.new(img.width, img.height, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(img.tobytes()), img.width * 3)
