"""Runs INSIDE Wine (Windows embeddable Python, ctypes only): drives the TJC editor with Win32 input, which Wine delivers
internally (GNOME blocks XWayland's synthetic XTEST input). Called from Linux by ../tjcui.py.

    python.exe winside.py windows
    python.exe winside.py click X Y [left|right|double]      screen coordinates
    python.exe winside.py text "any unicode"
    python.exe winside.py key ctrl+s | enter | alt+f | f5 ...
    python.exe winside.py focus "<title substring>"
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

u32 = ctypes.windll.user32
INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x2, 0x4
MOVE, LDOWN, LUP, RDOWN, RUP, ABSOLUTE = 0x1, 0x2, 0x4, 0x8, 0x10, 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wt.LONG), ("dy", wt.LONG), ("mouseData", wt.DWORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD), ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    u32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT))


def mouse(flags, x=0, y=0):
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(x, y, 0, flags, 0, 0)
    return i


def click(x, y, how="left"):
    sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
    nx, ny = int(x * 65535 / (sw - 1)), int(y * 65535 / (sh - 1))
    u32.SetCursorPos(int(x), int(y))
    send(mouse(MOVE | ABSOLUTE, nx, ny))
    time.sleep(0.05)
    down, up = (RDOWN, RUP) if how == "right" else (LDOWN, LUP)
    for _ in range(2 if how == "double" else 1):
        send(mouse(down | ABSOLUTE, nx, ny)); time.sleep(0.04)
        send(mouse(up | ABSOLUTE, nx, ny)); time.sleep(0.06)


def kb(vk=0, scan=0, flags=0):
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def text(s):
    for ch in s:
        for unit in ch.encode("utf-16-le").__iter__() if False else [ord(c) for c in ch.encode("utf-16-le").decode("utf-16-le")]:
            send(kb(0, unit, KEYEVENTF_UNICODE), kb(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
            time.sleep(0.01)


VK = {"ctrl": 0x11, "alt": 0x12, "shift": 0x10, "enter": 0x0D, "esc": 0x1B, "tab": 0x09, "space": 0x20, "del": 0x2E,
      "back": 0x08, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22}
VK.update({f"f{n}": 0x6F + n for n in range(1, 13)})


def vk_of(name):
    name = name.lower()
    if name in VK:
        return VK[name]
    if len(name) == 1:
        return u32.VkKeyScanW(ord(name)) & 0xFF
    raise ValueError(name)


def key(combo):
    codes = [vk_of(p) for p in combo.split("+")]
    send(*[kb(c) for c in codes])
    time.sleep(0.03)
    send(*[kb(c, 0, KEYEVENTF_KEYUP) for c in reversed(codes)])
    time.sleep(0.05)


def windows():
    out = []
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _):
        if u32.IsWindowVisible(h):
            n = u32.GetWindowTextLengthW(h)
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, buf, n + 1)
            r = wt.RECT(); u32.GetWindowRect(h, ctypes.byref(r))
            cls = ctypes.create_unicode_buffer(128); u32.GetClassNameW(h, cls, 128)
            if r.right - r.left > 1:
                out.append((h, buf.value, r.left, r.top, r.right - r.left, r.bottom - r.top, cls.value))
        return True
    u32.EnumWindows(PROC(cb), 0)
    return out


def focus(sub):
    for h, t, *_ in windows():
        if sub in t:
            u32.SetForegroundWindow(h)
            return True
    return False


def children(title):
    """Child controls of the top-level window with this exact title: (hwnd, class, x, y, w, h, text)."""
    top = next((h for h, t, *_ in windows() if t == title), None)
    out = []
    if not top:
        return out
    PROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

    def cb(h, _):
        n = u32.GetWindowTextLengthW(h)
        buf = ctypes.create_unicode_buffer(n + 1); u32.GetWindowTextW(h, buf, n + 1)
        cls = ctypes.create_unicode_buffer(128); u32.GetClassNameW(h, cls, 128)
        r = wt.RECT(); u32.GetWindowRect(h, ctypes.byref(r))
        out.append((h, cls.value, r.left, r.top, r.right - r.left, r.bottom - r.top, buf.value))
        return True
    u32.EnumChildWindows(top, PROC(cb), 0)
    return out


CB_GETCOUNT, CB_GETLBTEXT, CB_GETLBTEXTLEN, CB_SETCURSEL, CB_GETCURSEL = 0x146, 0x148, 0x149, 0x14E, 0x147
WM_COMMAND, CBN_SELCHANGE = 0x0111, 1


def combo_items(h):
    n = u32.SendMessageW(h, CB_GETCOUNT, 0, 0)
    items = []
    for i in range(max(0, n)):
        L = u32.SendMessageW(h, CB_GETLBTEXTLEN, i, 0)
        buf = ctypes.create_unicode_buffer(L + 1); u32.SendMessageW(h, CB_GETLBTEXT, i, buf)
        items.append(buf.value)
    return items


def combo_select(h, text):
    """Select the entry with exactly this text and notify the owner like a user pick (WM_COMMAND CBN_SELCHANGE)."""
    items = combo_items(h)
    if text not in items:
        raise SystemExit(f"not in list: {text!r} (have {len(items)} items)")
    i = items.index(text)
    u32.SendMessageW(h, CB_SETCURSEL, i, 0)
    cid = u32.GetDlgCtrlID(h)
    u32.SendMessageW(u32.GetParent(h), WM_COMMAND, (CBN_SELCHANGE << 16) | (cid & 0xFFFF), h)
    return i


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[0] == "windows":
        for h, t, x, y, w, hh, c in windows():
            print(f"{h}\t{x}\t{y}\t{w}\t{hh}\t{c}\t{t}")
    elif a[0] == "click":
        click(float(a[1]), float(a[2]), a[3] if len(a) > 3 else "left")
    elif a[0] == "text":
        text(a[1])
    elif a[0] == "key":
        for k in a[1:]:
            key(k)
    elif a[0] == "focus":
        print(focus(a[1]))
    elif a[0] == "children":
        for c in children(a[1]):
            print("\t".join(map(str, c)))
    elif a[0] == "items":
        print("\n".join(combo_items(int(a[1]))))
    elif a[0] == "select":
        print(combo_select(int(a[1]), a[2]))
    elif a[0] == "close":   # politely close windows whose title equals a[1] (WM_CLOSE)
        n = 0
        for h, t, *_ in windows():
            if t == a[1]:
                u32.PostMessageW(h, 0x0010, 0, 0); n += 1
        print(n)
