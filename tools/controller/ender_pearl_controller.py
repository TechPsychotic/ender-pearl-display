#!/usr/bin/env python3
"""Ender Pearl Display controller: a GNOME (GTK 4 / libadwaita) app on your PC for the printer's display, through the Pi.

  Live     the screen, mirrored live; the knob (buttons, arrow keys, scroll wheel); wallpaper, brightness, sleep,
           clock, messages, jump to a screen
  Flash    ask the display who it is, flash a .tft with progress, put Creality's firmware back
  Bench    raw TJC instructions to the display and its replies (the display service is paused meanwhile)
  Service  the display service (start / stop / restart), the link checks, the live log

    python3 tools/controller/ender_pearl_controller.py

Needs: PyGObject with GTK 4 and libadwaita (Fedora / GNOME have them), Pillow, ssh with key access to the Pi."""
import os
import sys
import threading
import time

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import mirror  # noqa: E402
import pi as P  # noqa: E402

APP_ID = "io.github.techpsychotic.EnderPearlController"
SCALE = 2                       # mirror pixels per display pixel
SLEEP_CHOICES = [(60, "1 min"), (120, "2 min"), (300, "5 min"), (600, "10 min"), (1800, "30 min"), (3600, "1 h")]
SCREENS = [("home", "Home"), ("print", "Print"), ("prepare", "Prepare"), ("control", "Control"), ("level", "Level")]
BENCH_PRESETS = [("Brightness?", "get dim"), ("Clear black", "cls 0"), ("Red box", "fill 20,60,200,80,63488"),
                 ("Teal circle", "cirs 120,220,40,11643"), ("Text", 'xstr 10,150,220,30,2,65535,0,1,1,1,"Hello from the bench"'),
                 ("Backlight 100", "dim=100"), ("Backlight 20", "dim=20")]
STOCK_HINT = "Creality's display firmware must be on the Pi at out/stock_display_fw/TJC_SET/tjc.tft (see docs/03-custom-firmware.md)."


def bg(fn, done=None, fail=None):
    """Run fn in a thread; done(result) / fail(error) on the GTK main loop."""
    def run():
        try:
            r = fn()
        except Exception as e:   # noqa: BLE001 - shown to the user
            if fail:
                GLib.idle_add(fail, e)
            return
        if done:
            GLib.idle_add(done, r)
    threading.Thread(target=run, daemon=True).start()


def texture(img):
    """A Pillow RGB image -> a Gdk texture."""
    data = img.tobytes()
    return Gdk.MemoryTexture.new(img.width, img.height, Gdk.MemoryFormat.R8G8B8, GLib.Bytes.new(data), img.width * 3)


def log_view():
    tv = Gtk.TextView(editable=False, cursor_visible=False, monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR,
                      top_margin=8, bottom_margin=8, left_margin=10, right_margin=10)
    sc = Gtk.ScrolledWindow(child=tv, vexpand=True, hexpand=True, min_content_height=200)
    sc.add_css_class("card")
    return tv, sc


def append(tv, text, follow=True):
    b = tv.get_buffer()
    b.insert(b.get_end_iter(), text)
    if b.get_line_count() > 3000:                     # keep it light
        b.delete(b.get_start_iter(), b.get_iter_at_line(b.get_line_count() - 2500)[1])
    if follow:
        tv.scroll_to_mark(b.create_mark(None, b.get_end_iter(), False), 0, False, 0, 1)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Ender Pearl Display", default_width=1080, default_height=760)
        self.cfg = P.load_config()
        self.pi = P.Pi(self.cfg)
        self.mirror = mirror.Mirror(self.pi)
        self.connected = False
        self.frame_v = None
        self.state = {}
        self.dcfg = None
        self.walls = None
        self.syncing = False
        self.bench = None
        self.logproc = None
        self.busy_flash = False

        self.toasts = Adw.ToastOverlay()
        tv = Adw.ToolbarView()
        hb = Adw.HeaderBar()
        self.stack = Adw.ViewStack()
        hb.set_title_widget(Adw.ViewSwitcher(stack=self.stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        self.conn_btn = Gtk.MenuButton(icon_name="network-wired-symbolic", tooltip_text="Connection")
        self.conn_btn.set_popover(self._conn_popover())
        hb.pack_start(self.conn_btn)
        self.status = Gtk.Label(label="not connected", css_classes=["dim-label"])
        hb.pack_end(self.status)
        tv.add_top_bar(hb)
        tv.set_content(self.stack)
        self.toasts.set_child(tv)
        self.set_content(self.toasts)

        self.stack.add_titled_with_icon(self._live_page(), "live", "Live", "video-display-symbolic")
        self.stack.add_titled_with_icon(self._flash_page(), "flash", "Flash", "system-software-install-symbolic")
        self.stack.add_titled_with_icon(self._bench_page(), "bench", "Bench", "utilities-terminal-symbolic")
        self.stack.add_titled_with_icon(self._service_page(), "service", "Service", "preferences-system-symbolic")
        self.stack.connect("notify::visible-child-name", lambda *a: self._page_changed())

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self.connect("close-request", self._closing)
        GLib.timeout_add(700, self._tick)
        GLib.idle_add(self.do_connect)

    # ================================================================ connection
    def _conn_popover(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=10, margin_bottom=10, margin_start=10, margin_end=10)
        grp = Adw.PreferencesGroup(title="Raspberry Pi")
        self.e_host = Adw.EntryRow(title="Host or IP", text=self.cfg["host"])
        self.e_user = Adw.EntryRow(title="SSH user", text=self.cfg["user"])
        self.e_root = Adw.EntryRow(title="Project folder (in home)", text=self.cfg["root"])
        for r in (self.e_host, self.e_user, self.e_root):
            grp.add(r)
        box.append(grp)
        row = Gtk.Box(spacing=6, homogeneous=True)
        b1 = Gtk.Button(label="Connect", css_classes=["suggested-action"])
        b1.connect("clicked", lambda *_: self.do_connect())
        b2 = Gtk.Button(label="Find the Pi")
        b2.set_tooltip_text("Ping the local network and look for the Pi's MAC address")
        b2.connect("clicked", lambda *_: self.do_find())
        row.append(b2)
        row.append(b1)
        box.append(row)
        self.conn_note = Gtk.Label(wrap=True, xalign=0, css_classes=["dim-label", "caption"], max_width_chars=40)
        box.append(self.conn_note)
        return Gtk.Popover(child=box)

    def toast(self, text, secs=4):
        t = Adw.Toast(title=GLib.markup_escape_text(str(text)))
        t.set_timeout(secs)
        self.toasts.add_toast(t)

    def do_connect(self):
        self.cfg.update(host=self.e_host.get_text().strip() or "raspberrypi.local", user=self.e_user.get_text().strip() or "rpi4",
                        root=self.e_root.get_text().strip() or "closedloop")
        self.status.set_label("connecting…")
        self.conn_note.set_label("")

        def ok(state):
            self.connected, self.state, self.frame_v = True, state, None
            P.save_config(self.cfg)
            self.status.set_label(f"{self.cfg['host']} · {'printing' if state.get('printing') else 'idle'}")
            self.toast(f"Connected to {self.cfg['host']}")
            self.load_display_config()
            self.refresh_service()
            self._page_changed()

        def bad(e):
            self.connected = False
            self.status.set_label("not connected")
            self.conn_note.set_label(f"{e}\nTry “Find the Pi” if its address changed.")
            self.conn_btn.popup()
        bg(self.pi.connect, ok, bad)
        return False

    def do_find(self):
        self.conn_note.set_label("Pinging the local network…")

        def ok(ip):
            if not ip:
                self.conn_note.set_label("No Raspberry Pi found on this network.")
                return
            self.e_host.set_text(ip)
            self.conn_note.set_label(f"Found it at {ip}.")
            self.do_connect()
        bg(lambda: P.Pi.find(self.cfg.get("mac", "")), ok, lambda e: self.conn_note.set_label(str(e)))

    def need(self, idle=False):
        if not self.connected:
            self.toast("Not connected to the Pi")
            return False
        if idle and (self.state.get("printing") or self.state.get("sd")):
            self.toast("The printer is printing: wait until it has finished")
            return False
        return True

    def confirm(self, heading, body, label, then, destructive=True):
        d = Adw.AlertDialog(heading=heading, body=body)
        d.add_response("cancel", "Cancel")
        d.add_response("go", label)
        d.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE if destructive else Adw.ResponseAppearance.SUGGESTED)
        d.set_default_response("cancel")
        d.set_close_response("cancel")
        d.connect("response", lambda _d, r: then() if r == "go" else None)
        d.present(self)

    # ================================================================ Live
    def _live_page(self):
        page = Gtk.Box(spacing=24, margin_top=18, margin_bottom=18, margin_start=24, margin_end=24)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, valign=Gtk.Align.START)
        self.screen = Gtk.Picture(can_shrink=False, content_fit=Gtk.ContentFit.FILL)
        self.screen.set_size_request(240 * SCALE, 320 * SCALE)
        frame = Gtk.Frame(child=self.screen, css_classes=["card"])
        scroll = Gtk.EventControllerScroll(flags=Gtk.EventControllerScrollFlags.VERTICAL | Gtk.EventControllerScrollFlags.DISCRETE)
        scroll.connect("scroll", lambda _c, dx, dy: (self.knob("turn", 1 if dy > 0 else -1), True)[1])
        frame.add_controller(scroll)
        left.append(frame)
        self.screen_note = Gtk.Label(label="", css_classes=["dim-label", "caption"])
        left.append(self.screen_note)
        knob = Gtk.Box(spacing=8, homogeneous=True)
        for label, icon, tip, op, d in (("Up", "go-up-symbolic", "Turn back (↑ / ←)", "turn", -1),
                                        ("Down", "go-down-symbolic", "Turn on (↓ / →)", "turn", 1),
                                        ("Press", "object-select-symbolic", "Press the knob (Enter / Space)", "press", None),
                                        ("Back", "go-previous-symbolic", "Hold the knob: back (Esc / Backspace)", "long", None)):
            b = Gtk.Button(tooltip_text=tip)
            b.set_child(Adw.ButtonContent(icon_name=icon, label=label))
            b.connect("clicked", lambda _b, op=op, d=d: self.knob(op, d))
            knob.append(b)
        left.append(knob)
        left.append(Gtk.Label(label="Keys: arrows turn · Enter presses · Esc goes back · scroll on the screen turns",
                              css_classes=["dim-label", "caption"], wrap=True))
        page.append(left)

        right = Adw.PreferencesPage(hexpand=True)
        g = Adw.PreferencesGroup(title="Printer")
        self.row_state = Adw.ActionRow(title="State", subtitle="–")
        self.row_temp = Adw.ActionRow(title="Temperatures", subtitle="–")
        g.add(self.row_state)
        g.add(self.row_temp)
        right.add(g)

        g = Adw.PreferencesGroup(title="Display", description="Saved on the Pi; the screen picks them up within a few seconds")
        self.row_wall = Adw.ComboRow(title="Wallpaper", model=Gtk.StringList())
        self.row_wall.connect("notify::selected", lambda *_: self.set_dcfg(wallpaper=self._wall_name()))
        self.row_bright = Adw.SpinRow.new_with_range(10, 100, 5)
        self.row_bright.set_title("Brightness (%)")
        self.row_bright.connect("notify::value", lambda *_: self._debounced("bright", lambda: self.set_dcfg(brightness=int(self.row_bright.get_value()))))
        self.row_sleep = Adw.ComboRow(title="Sleep after", model=Gtk.StringList.new([s for _, s in SLEEP_CHOICES]))
        self.row_sleep.connect("notify::selected", lambda *_: self.set_dcfg(sleep_s=SLEEP_CHOICES[self.row_sleep.get_selected()][0]))
        self.row_clock = Adw.SwitchRow(title="24-hour clock")
        self.row_clock.connect("notify::active", lambda *_: self.set_dcfg(clock24=self.row_clock.get_active()))
        for r in (self.row_wall, self.row_bright, self.row_sleep, self.row_clock):
            g.add(r)
        right.add(g)

        g = Adw.PreferencesGroup(title="Message", description="Shown on the screen (and wakes it)")
        self.row_msg = Adw.EntryRow(title="Text", show_apply_button=True)
        self.row_msg.connect("apply", lambda *_: self.send_message())
        g.add(self.row_msg)
        right.add(g)

        g = Adw.PreferencesGroup(title="Go to a screen")
        row = Gtk.Box(spacing=6, homogeneous=True, margin_top=4)
        for key, label in SCREENS:
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, k=key: self.show_screen(k))
            row.append(b)
        g.add(row)
        right.add(g)
        page.append(right)
        return page

    def _wall_name(self):
        i = self.row_wall.get_selected()
        return self.walls["names"][i] if self.walls and 0 <= i < len(self.walls["names"]) else None

    def _debounced(self, key, fn, ms=500):
        if self.syncing:
            return
        tid = getattr(self, "_deb_" + key, None)
        if tid:
            GLib.source_remove(tid)

        def fire():
            setattr(self, "_deb_" + key, None)
            fn()
            return False
        setattr(self, "_deb_" + key, GLib.timeout_add(ms, fire))

    def load_display_config(self):
        def get():
            return self.pi.api("GET", "/api/display/config"), self.pi.api("GET", "/api/display/wallpapers")

        def ok(r):
            self.dcfg, self.walls = r
            self.syncing = True
            self.row_wall.set_model(Gtk.StringList.new([self.walls["titles"][n] for n in self.walls["names"]]))
            if self.dcfg.get("wallpaper") in self.walls["names"]:
                self.row_wall.set_selected(self.walls["names"].index(self.dcfg["wallpaper"]))
            self.row_bright.set_value(self.dcfg.get("brightness", 80))
            secs = [s for s, _ in SLEEP_CHOICES]
            sl = self.dcfg.get("sleep_s", 600)
            self.row_sleep.set_selected(min(range(len(secs)), key=lambda i: abs(secs[i] - sl)))
            self.row_clock.set_active(bool(self.dcfg.get("clock24", True)))
            self.syncing = False
        bg(get, ok, lambda e: self.toast(e))

    def set_dcfg(self, **kw):
        if self.syncing or not self.connected or any(v is None for v in kw.values()):
            return
        bg(lambda: self.pi.api("POST", "/api/display/config", kw), lambda c: setattr(self, "dcfg", c), lambda e: self.toast(e))

    def send_message(self):
        text = self.row_msg.get_text().strip()
        if text and self.need():
            bg(lambda: self.pi.api("POST", "/api/display/config", {"message": text}),
               lambda _r: (self.row_msg.set_text(""), self.toast("Message sent")), lambda e: self.toast(e))

    def show_screen(self, key):
        if self.need():
            bg(lambda: self.pi.api("POST", "/api/display/config", {"show": key}), None, lambda e: self.toast(e))

    def knob(self, op, d=None):
        if self.need():
            bg(lambda: self.pi.knob(op, d), lambda _r: self._poll_frame(), lambda e: self.toast(e))

    def _key(self, _c, keyval, _code, state):
        if self.stack.get_visible_child_name() != "live" or isinstance(self.get_focus(), (Gtk.Text, Gtk.Entry)):
            return False
        k = Gdk.keyval_name(keyval)
        if k in ("Up", "Left"):
            self.knob("turn", -1)
        elif k in ("Down", "Right"):
            self.knob("turn", 1)
        elif k in ("Return", "KP_Enter", "space"):
            self.knob("press")
        elif k in ("Escape", "BackSpace"):
            self.knob("long")
        else:
            return False
        return True

    def _poll_frame(self):
        def get():
            fr = self.pi.api("GET", "/api/display/frame", timeout=5)
            if fr.get("v") is None or fr.get("v") == self.frame_v:
                return fr, None
            return fr, self.mirror.render(fr).resize((240 * SCALE, 320 * SCALE), 0)

        def ok(r):
            fr, img = r
            if img is not None:
                self.frame_v = fr["v"]
                self.screen.set_paintable(texture(img))
            age = time.time() - fr["t"] if fr.get("t") else None
            self.screen_note.set_label("the display app hasn't reported yet" if fr.get("v") is None else
                                       "asleep: the screen is off (any knob action wakes it)" if fr.get("dimmed") else
                                       f"live · {len(fr.get('cmds') or [])} drawing commands" + (f" · unchanged for {age:.0f} s" if age and age > 30 else ""))
        if not getattr(self, "_polling", False):
            self._polling = True

            def done(r):
                self._polling = False
                ok(r)

            def fail(e):
                self._polling = False
                self.screen_note.set_label(f"no picture: {e}")
            bg(get, done, fail)

    def _poll_state(self):
        def ok(st):
            self.state = st
            s = st.get("status") or {}
            if st.get("printing"):
                pct = 100 * s.get("sent", 0) / s["total"] if s.get("total") else 0
                self.row_state.set_subtitle(f"printing {st.get('job') or ''} · layer {s.get('layer', -1) + 1}/{s.get('layers', '?')} · {pct:.0f} % of the G-code sent")
            else:
                fam = (st.get("filament") or {}).get("family")
                self.row_state.set_subtitle(f"idle · {fam + ' loaded' if fam else 'no filament'}")
            t = s.get("temps") if st.get("printing") else st.get("idle_temps")
            self.row_temp.set_subtitle(f"nozzle {t[0]:.0f} / {t[1]:.0f} °C · bed {t[2]:.0f} / {t[3]:.0f} °C" if t else "printer not connected")
            self.status.set_label(f"{self.cfg['host']} · {'printing' if st.get('printing') else 'idle'}")
        bg(lambda: self.pi.api("GET", "/api/state", timeout=5), ok, lambda e: self.status.set_label(f"{self.cfg['host']} · {e}"))

    def _tick(self):
        if self.connected:
            page = self.stack.get_visible_child_name()
            if page == "live" and not self.bench:
                self._poll_frame()
            self._n = getattr(self, "_n", 0) + 1
            if self._n % 3 == 0:
                self._poll_state()
        return True

    def _page_changed(self):
        if self.stack.get_visible_child_name() == "service" and self.connected:
            self.refresh_service()
            self.start_log()

    # ================================================================ Flash
    def _flash_page(self):
        page = Adw.PreferencesPage()
        g = Adw.PreferencesGroup(title="The display", description="Asking writes nothing. The display service pauses for a few seconds.")
        self.row_probe = Adw.ActionRow(title="Model, firmware, flash", subtitle="not asked yet")
        b = Gtk.Button(label="Ask", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda *_: self.do_probe())
        self.row_probe.add_suffix(b)
        g.add(self.row_probe)
        page.add(g)

        g = Adw.PreferencesGroup(title="Flash firmware", description="A .tft built for the TJC3224T132_011N. The print, if any, is not affected, "
                                 "but flashing is only offered while the printer is idle.")
        default = os.path.join(REPO, "firmware", "glass.tft")
        self.tft = default if os.path.exists(default) else None
        self.row_file = Adw.ActionRow(title="File", subtitle=self.tft or "choose a .tft")
        b = Gtk.Button(label="Choose…", valign=Gtk.Align.CENTER)
        b.connect("clicked", lambda *_: self.choose_tft())
        self.row_file.add_suffix(b)
        g.add(self.row_file)
        row = Adw.ActionRow(title="Flash it", subtitle="Uploads the file to the Pi, then to the display over UART3 at 921600 baud")
        self.btn_flash = Gtk.Button(label="Flash", valign=Gtk.Align.CENTER, css_classes=["suggested-action"])
        self.btn_flash.connect("clicked", lambda *_: self.do_flash(stock=False))
        row.add_suffix(self.btn_flash)
        g.add(row)
        row = Adw.ActionRow(title="Back to Creality's firmware", subtitle=STOCK_HINT)
        self.btn_stock = Gtk.Button(label="Restore", valign=Gtk.Align.CENTER, css_classes=["destructive-action"])
        self.btn_stock.connect("clicked", lambda *_: self.do_flash(stock=True))
        row.add_suffix(self.btn_stock)
        g.add(row)
        page.add(g)

        g = Adw.PreferencesGroup(title="Progress")
        self.progress = Gtk.ProgressBar(show_text=True, margin_top=6, margin_bottom=6)
        self.progress.set_text("idle")
        g.add(self.progress)
        self.flash_log, sc = log_view()
        sc.set_min_content_height(180)
        g.add(sc)
        page.add(g)
        return page

    def choose_tft(self):
        d = Gtk.FileDialog(title="Choose a .tft")
        f = Gtk.FileFilter(name="TJC firmware (*.tft)")
        f.add_pattern("*.tft")
        store = Gio.ListStore.new(Gtk.FileFilter)
        store.append(f)
        d.set_filters(store)
        if self.tft:
            d.set_initial_folder(Gio.File.new_for_path(os.path.dirname(self.tft)))

        def done(dlg, res):
            try:
                self.tft = dlg.open_finish(res).get_path()
                self.row_file.set_subtitle(self.tft)
            except GLib.Error:
                pass
        d.open(self, None, done)

    def _flash_cmd(self, args):
        """flash.py at the display's current baud: 921600 (our firmware after the app ran), else 115200."""
        return (f"python3 -u display/flash.py {args} --baud 921600 2>&1 | tee /tmp/epc_flash.log; "
                f"grep -q 'no .comok' /tmp/epc_flash.log && python3 -u display/flash.py {args} --baud 115200 2>&1")

    def do_probe(self):
        if not self.need(idle=True):
            return
        self.row_probe.set_subtitle("asking…")

        def ok(r):
            rc, out, err = r
            line = next((l for l in out.splitlines() if l.startswith("display:")), None)
            if not line:
                self.row_probe.set_subtitle((out or err).strip().splitlines()[-1] if (out or err).strip() else "no answer")
                return
            f = line.split("comok", 1)[1].strip().split(",") if "comok" in line else []
            nice = f"{f[2]} · runtime {f[3]} · {int(f[-1]) // 1048576} MB flash" if len(f) >= 7 else line
            self.row_probe.set_subtitle(nice)
        bg(lambda: self.pi.run(self._flash_cmd("--probe"), timeout=60), ok, lambda e: self.row_probe.set_subtitle(str(e)))

    def do_flash(self, stock):
        if self.busy_flash or not self.need(idle=True):
            return
        if not stock and not self.tft:
            self.toast("Choose a .tft first")
            return
        name = "Creality's stock firmware" if stock else os.path.basename(self.tft)
        body = (f"Flash {name} to the printer's display? The screen goes blank for about a minute and restarts with the new firmware. "
                + ("With Creality's firmware the Ender Pearl screen stops working until you flash it again; the display service is stopped afterwards."
                   if stock else "Only for the TJC3224T132_011N."))
        self.confirm("Flash the display?", body, "Flash", lambda: self._flash_run(stock))

    def _flash_run(self, stock):
        self.busy_flash = True
        self.btn_flash.set_sensitive(False)
        self.btn_stock.set_sensitive(False)
        self.flash_log.get_buffer().set_text("")
        self.progress.set_fraction(0)
        self.progress.set_text("uploading to the Pi…")

        def work():
            if stock:
                args = "--stock"
            else:
                remote = "out/display_fw/" + os.path.basename(self.tft).replace(" ", "_")
                self.pi.run("mkdir -p out/display_fw")
                self.pi.scp(self.tft, remote)
                args = remote
            p = self.pi.popen(self._flash_cmd(args))
            for line in p.stdout:
                GLib.idle_add(self._flash_line, line)
            p.wait()
            if stock:   # our app can't talk to Creality's firmware: don't leave it retrying
                self.pi.run("systemctl --user stop ender-loop-display")
            return p.returncode

        def done(rc):
            self.busy_flash = False
            self.btn_flash.set_sensitive(True)
            self.btn_stock.set_sensitive(True)
            ok = "done in" in self.flash_log.get_buffer().get_property("text")
            self.progress.set_fraction(1 if ok else self.progress.get_fraction())
            self.progress.set_text("done" if ok else "failed: see the log")
            self.toast("Display flashed" if ok else "Flashing failed", 6)
            self.frame_v = None

        def fail(e):
            done(1)
            append(self.flash_log, f"\n{e}\n")
        bg(work, done, fail)

    def _flash_line(self, line):
        append(self.flash_log, line)
        s = line.strip()
        if s.endswith("%") and s[:-1].isdigit():
            self.progress.set_fraction(int(s[:-1]) / 100)
            self.progress.set_text(s)
        elif s.startswith("flashing"):
            self.progress.set_text("flashing…")

    # ================================================================ Bench
    def _bench_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=18, margin_start=24, margin_end=24)
        top = Gtk.Box(spacing=10)
        self.bench_btn = Gtk.Button(label="Start the bench", css_classes=["suggested-action"])
        self.bench_btn.connect("clicked", lambda *_: self.toggle_bench())
        top.append(self.bench_btn)
        self.bench_note = Gtk.Label(label="Pauses the display service and talks to the display directly. Stopping the bench resumes it.",
                                    css_classes=["dim-label"], wrap=True, xalign=0, hexpand=True)
        top.append(self.bench_note)
        page.append(top)
        row = Gtk.Box(spacing=8)
        self.bench_entry = Gtk.Entry(placeholder_text='a TJC instruction, e.g.  fill 0,0,240,320,0   or   xstr 10,10,200,30,1,65535,0,0,1,1,"hi"', hexpand=True)
        self.bench_entry.connect("activate", lambda *_: self.bench_send(self.bench_entry.get_text()))
        row.append(self.bench_entry)
        b = Gtk.Button(label="Send")
        b.connect("clicked", lambda *_: self.bench_send(self.bench_entry.get_text()))
        row.append(b)
        page.append(row)
        flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, max_children_per_line=8, column_spacing=6, row_spacing=6)
        for label, cmd in BENCH_PRESETS:
            b = Gtk.Button(label=label, tooltip_text=cmd)
            b.connect("clicked", lambda _b, c=cmd: self.bench_send(c))
            flow.append(b)
        page.append(flow)
        self.bench_log, sc = log_view()
        page.append(sc)
        page.append(Gtk.Label(label="Colours are RGB565 numbers (white 65535, red 63488, teal 11643). Fonts 0–6, pictures by id: "
                                    "design/assets/manifest.json. Every reply is shown: ok, an error name, a number or a string.",
                              css_classes=["dim-label", "caption"], wrap=True, xalign=0))
        return page

    def toggle_bench(self):
        if self.bench:
            self.stop_bench()
        elif self.need(idle=True):
            self.confirm("Start the bench?", "The Ender Pearl screen stops while the bench runs: the display shows only what you send. "
                         "Stopping the bench starts the screen again.", "Start", self.start_bench, destructive=False)

    def start_bench(self):
        self.bench_btn.set_sensitive(False)
        append(self.bench_log, "stopping the display service…\n")

        def work():
            self.pi.run("systemctl --user stop ender-loop-display")
            return self.pi.popen("python3 -u display/bench.py", stdin=True)

        def ok(p):
            self.bench = p
            self.bench_btn.set_label("Stop the bench")
            self.bench_btn.set_css_classes(["destructive-action"])
            self.bench_btn.set_sensitive(True)
            threading.Thread(target=self._bench_reader, args=(p,), daemon=True).start()
        bg(work, ok, lambda e: (append(self.bench_log, f"{e}\n"), self.bench_btn.set_sensitive(True)))

    def _bench_reader(self, p):
        import json
        for line in p.stdout:
            try:
                m = json.loads(line)
            except ValueError:
                GLib.idle_add(append, self.bench_log, line)
                continue
            if "ready" in m:
                txt = f"display {'ready' if m['ready'] else 'NOT answering'} on {m.get('port')} at {m.get('baud')} baud\n"
            else:
                reps = ", ".join("ok" if r.get("ok") else f"= {r['number']}" if "number" in r else f"= \"{r['string']}\"" if "string" in r
                                 else f"ERROR {r.get('name')}" for r in m.get("replies") or []) or "no reply"
                txt = f"> {m.get('cmd')}\n  {reps}   ({m.get('ms')} ms)\n"
            GLib.idle_add(append, self.bench_log, txt)
        GLib.idle_add(append, self.bench_log, "bench ended\n")

    def bench_send(self, cmd):
        cmd = cmd.strip()
        if not cmd:
            return
        if not self.bench:
            self.toast("Start the bench first")
            return
        try:
            self.bench.stdin.write(cmd + "\n")
            self.bench.stdin.flush()
        except (OSError, ValueError) as e:
            self.toast(f"bench: {e}")

    def stop_bench(self):
        p, self.bench = self.bench, None
        self.bench_btn.set_sensitive(False)

        def work():
            try:
                p.stdin.close()
                p.wait(timeout=5)
            except Exception:   # noqa: BLE001
                p.kill()
            self.pi.run("systemctl --user start ender-loop-display")

        def ok(_r):
            self.bench_btn.set_label("Start the bench")
            self.bench_btn.set_css_classes(["suggested-action"])
            self.bench_btn.set_sensitive(True)
            self.frame_v = None
            append(self.bench_log, "display service started again\n")
        bg(work, ok, lambda e: (self.toast(e), self.bench_btn.set_sensitive(True)))

    # ================================================================ Service
    def _service_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=18, margin_bottom=18, margin_start=24, margin_end=24)
        g = Adw.PreferencesGroup(title="Status")
        self.rows = {}
        for key, title in (("display", "Display service (ender-loop-display)"), ("server", "Web server (ender-loop)"),
                           ("uart", "UART3 (dtoverlay=uart3)"), ("tty", "Serial port"), ("link", "Last link message")):
            r = Adw.ActionRow(title=title, subtitle="–")
            self.rows[key] = r
            g.add(r)
        row = Gtk.Box(spacing=6, margin_top=8)
        for label, act in (("Start", "start"), ("Stop", "stop"), ("Restart", "restart")):
            b = Gtk.Button(label=f"{label} display")
            b.connect("clicked", lambda _b, a=act: self.service(a))
            row.append(b)
        b = Gtk.Button(label="Restart web server", css_classes=["destructive-action"])
        b.set_tooltip_text("Only while the printer is idle")
        b.connect("clicked", lambda *_: self.restart_server())
        row.append(b)
        b = Gtk.Button(label="Refresh", halign=Gtk.Align.END, hexpand=True)
        b.connect("clicked", lambda *_: self.refresh_service())
        row.append(b)
        g.add(row)
        page.append(g)
        head = Gtk.Box(spacing=8)
        head.append(Gtk.Label(label="Display log (out/display.log)", css_classes=["heading"], xalign=0, hexpand=True))
        self.follow = Gtk.CheckButton(label="Follow", active=True)
        head.append(self.follow)
        page.append(head)
        self.svc_log, sc = log_view()
        page.append(sc)
        return page

    def refresh_service(self):
        cmd = ("echo display=$(systemctl --user is-active ender-loop-display); echo server=$(systemctl --user is-active ender-loop); "
               "echo uart=$(grep -hs '^dtoverlay=uart3' /boot/firmware/config.txt /boot/config.txt | head -1); "
               "for d in /sys/class/tty/ttyAMA*; do readlink -f $d/device/of_node | grep -q 7e201600 && echo tty=/dev/$(basename $d); done; "
               "echo link=$(grep -a 'display' out/display.log | tail -1)")

        def ok(r):
            rc, out, err = r
            v = dict(l.split("=", 1) for l in out.splitlines() if "=" in l)
            self.rows["display"].set_subtitle(v.get("display", "?"))
            self.rows["server"].set_subtitle(v.get("server", "?"))
            self.rows["uart"].set_subtitle("enabled" if v.get("uart") else "not found in config.txt")
            self.rows["tty"].set_subtitle(v.get("tty", "UART3 has no tty (enable dtoverlay=uart3 and reboot)"))
            self.rows["link"].set_subtitle(v.get("link") or "–")
        bg(lambda: self.pi.run(cmd), ok, lambda e: self.toast(e))

    def service(self, action):
        if not self.need():
            return
        if self.bench:
            self.toast("Stop the bench first")
            return
        bg(lambda: self.pi.run(f"systemctl --user {action} ender-loop-display"),
           lambda r: (self.toast(f"Display service: {action}" if not r[0] else (r[2] or r[1]).strip()), GLib.timeout_add(1500, lambda: self.refresh_service())),
           lambda e: self.toast(e))

    def restart_server(self):
        if not self.need(idle=True):
            return
        def work():
            if self.pi.printing():   # checked again right before: a print may have started meanwhile
                raise RuntimeError("the printer is printing: the web server was not restarted")
            return self.pi.run("systemctl --user restart ender-loop")

        def ok(_r):
            self.toast("Web server restarted")
            GLib.timeout_add(3000, lambda: self.refresh_service())
        self.confirm("Restart the web server?", "The web UI and the screen lose the printer for a few seconds. Never do this during a print.",
                     "Restart", lambda: bg(work, ok, lambda e: self.toast(e)))

    def start_log(self):
        if self.logproc and self.logproc.poll() is None:
            return
        self.svc_log.get_buffer().set_text("")
        self.logproc = self.pi.popen("tail -n 200 -F out/display.log")
        p = self.logproc

        def reader():
            for line in p.stdout:
                GLib.idle_add(lambda l=line: append(self.svc_log, l, self.follow.get_active()))
        threading.Thread(target=reader, daemon=True).start()

    def _closing(self, *_):
        if self.bench:   # never leave the screen paused: end the bench and start the display service, now
            p, self.bench = self.bench, None
            try:
                p.stdin.close()
                p.wait(timeout=5)
            except Exception:   # noqa: BLE001
                p.kill()
            self.pi.run("systemctl --user start ender-loop-display", timeout=15)
        if self.logproc:
            self.logproc.terminate()
        return False

    def snapshot(self, path):
        """Save the window as a PNG (EPC_SNAPSHOT=path: screenshots for the docs, checks on Wayland)."""
        w, h = self.get_width(), self.get_height()
        snap = Gtk.Snapshot()
        Gtk.WidgetPaintable.new(self).snapshot(snap, w, h)
        node = snap.to_node()
        if node:
            self.get_native().get_renderer().render_texture(node, None).save_to_png(path)
        return False


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)

    def do_activate(self):
        w = self.props.active_window or Window(self)
        w.present()
        shot = os.environ.get("EPC_SNAPSHOT")   # path[,page[,seconds]]: save a screenshot, then quit
        if shot:
            path, page, secs = (shot.split(",") + ["live", "6"])[:3]
            GLib.timeout_add(500, lambda: (w.stack.set_visible_child_name(page), False)[1])
            GLib.timeout_add(int(float(secs) * 1000), lambda: (w.snapshot(path), self.quit(), False)[2])


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
