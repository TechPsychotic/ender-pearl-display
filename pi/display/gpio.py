"""GPIO through the Linux GPIO character device (uAPI v2), standard library only: the Pi has no gpiod/gpiozero/RPi.GPIO
Python packages, and installing them needs sudo. On the Pi 4 the header GPIOs are lines 0–57 of /dev/gpiochip0 with
BCM numbering (line 19 = GPIO19 = pin 35).

Used for the display's knob: A, B and ENTER are switches to GND (the stock mainboard reads them with internal pull-ups:
encoder_pins ^PA12, ^PA11, click ^!PB1), so they are requested as inputs with the Pi's internal pull-up, both edges."""
import ctypes
import fcntl
import os
import select
import struct

CHIP = "/dev/gpiochip0"

# linux/gpio.h (uAPI v2)
FLAG_USED, FLAG_INPUT, FLAG_OUTPUT = 1 << 0, 1 << 2, 1 << 3
FLAG_EDGE_RISING, FLAG_EDGE_FALLING = 1 << 4, 1 << 5
FLAG_BIAS_PULL_UP, FLAG_BIAS_PULL_DOWN, FLAG_BIAS_DISABLED = 1 << 8, 1 << 9, 1 << 10
ATTR_ID_DEBOUNCE = 3
EVENT_RISING, EVENT_FALLING = 1, 2


def _iowr(nr, size):
    return (3 << 30) | (size << 16) | (0xB4 << 8) | nr


def _ior(nr, size):
    return (2 << 30) | (size << 16) | (0xB4 << 8) | nr


class _Attr(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("padding", ctypes.c_uint32), ("value", ctypes.c_uint64)]


class _ConfigAttr(ctypes.Structure):
    _fields_ = [("attr", _Attr), ("mask", ctypes.c_uint64)]


class _LineConfig(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("num_attrs", ctypes.c_uint32), ("padding", ctypes.c_uint32 * 5),
                ("attrs", _ConfigAttr * 10)]


class _LineRequest(ctypes.Structure):
    _fields_ = [("offsets", ctypes.c_uint32 * 64), ("consumer", ctypes.c_char * 32), ("config", _LineConfig),
                ("num_lines", ctypes.c_uint32), ("event_buffer_size", ctypes.c_uint32), ("padding", ctypes.c_uint32 * 5),
                ("fd", ctypes.c_int32)]


class _LineInfo(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char * 32), ("consumer", ctypes.c_char * 32), ("offset", ctypes.c_uint32),
                ("num_attrs", ctypes.c_uint32), ("flags", ctypes.c_uint64), ("attrs", _Attr * 10), ("padding", ctypes.c_uint32 * 4)]


class _LineValues(ctypes.Structure):
    _fields_ = [("bits", ctypes.c_uint64), ("mask", ctypes.c_uint64)]


class _ChipInfo(ctypes.Structure):
    _fields_ = [("name", ctypes.c_char * 32), ("label", ctypes.c_char * 32), ("lines", ctypes.c_uint32)]


assert ctypes.sizeof(_LineRequest) == 592 and ctypes.sizeof(_LineInfo) == 256 and ctypes.sizeof(_LineConfig) == 272
GET_CHIPINFO = _ior(0x01, ctypes.sizeof(_ChipInfo))
GET_LINEINFO = _iowr(0x05, ctypes.sizeof(_LineInfo))
GET_LINE = _iowr(0x07, ctypes.sizeof(_LineRequest))
LINE_GET_VALUES = _iowr(0x0E, ctypes.sizeof(_LineValues))
EVENT_SIZE = 48   # struct gpio_v2_line_event


def chip_info(chip=CHIP):
    fd = os.open(chip, os.O_RDONLY)
    try:
        ci = _ChipInfo(); fcntl.ioctl(fd, GET_CHIPINFO, ci)
        return {"name": ci.name.decode(), "label": ci.label.decode(), "lines": ci.lines}
    finally:
        os.close(fd)


def line_info(offset, chip=CHIP):
    """Name, consumer and flags of one line: shows whether something (a driver, an overlay) already uses it."""
    fd = os.open(chip, os.O_RDONLY)
    try:
        li = _LineInfo(); li.offset = offset; fcntl.ioctl(fd, GET_LINEINFO, li)
        f = li.flags
        return {"offset": offset, "name": li.name.decode(), "consumer": li.consumer.decode(), "used": bool(f & FLAG_USED),
                "dir": "out" if f & FLAG_OUTPUT else "in", "bias": "up" if f & FLAG_BIAS_PULL_UP else "down" if f & FLAG_BIAS_PULL_DOWN else "none"}
    finally:
        os.close(fd)


class Lines:
    """Inputs with pull-up and edge events. values() → {offset: 0/1}; events(timeout) → [(offset, rising, t_ns)]."""

    def __init__(self, offsets, consumer="ender-loop", pull="up", debounce_us=0, chip=CHIP):
        self.offsets = list(offsets)
        req = _LineRequest()
        for i, o in enumerate(self.offsets):
            req.offsets[i] = o
        req.num_lines = len(self.offsets)
        req.consumer = consumer.encode()[:31]
        bias = {"up": FLAG_BIAS_PULL_UP, "down": FLAG_BIAS_PULL_DOWN, None: FLAG_BIAS_DISABLED}[pull]
        req.config.flags = FLAG_INPUT | FLAG_EDGE_RISING | FLAG_EDGE_FALLING | bias
        if debounce_us:
            req.config.num_attrs = 1
            req.config.attrs[0].attr.id = ATTR_ID_DEBOUNCE
            req.config.attrs[0].attr.value = debounce_us
            req.config.attrs[0].mask = (1 << len(self.offsets)) - 1
        fd = os.open(chip, os.O_RDONLY)
        try:
            fcntl.ioctl(fd, GET_LINE, req)
        finally:
            os.close(fd)
        self.fd = req.fd

    def values(self):
        v = _LineValues(); v.mask = (1 << len(self.offsets)) - 1
        fcntl.ioctl(self.fd, LINE_GET_VALUES, v)
        return {o: (v.bits >> i) & 1 for i, o in enumerate(self.offsets)}

    def events(self, timeout=None):
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return []
        data, out = os.read(self.fd, EVENT_SIZE * 16), []
        for k in range(0, len(data) - EVENT_SIZE + 1, EVENT_SIZE):
            ts, eid, off = struct.unpack_from("<QII", data, k)
            out.append((off, eid == EVENT_RISING, ts))
        return out

    def close(self):
        os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class Quadrature:
    """Rotary encoder decoder (Gray-code transition table): feed (a, b) levels, get -1 / 0 / +1 per full detent.
    Invalid jumps (both lines changed: a missed edge) are ignored instead of counted."""
    _T = {(0b00, 0b01): 1, (0b01, 0b11): 1, (0b11, 0b10): 1, (0b10, 0b00): 1,
          (0b00, 0b10): -1, (0b10, 0b11): -1, (0b11, 0b01): -1, (0b01, 0b00): -1}

    def __init__(self, steps_per_detent=4):
        self.state, self.acc, self.spd = None, 0, steps_per_detent

    def feed(self, a, b):
        s = (a << 1) | b
        if self.state is None:
            self.state = s
            return 0
        step = self._T.get((self.state, s), 0)
        self.state = s
        self.acc += step
        if abs(self.acc) >= self.spd:
            d = 1 if self.acc > 0 else -1
            self.acc = 0
            return d
        return 0


LINE_SET_VALUES = _iowr(0x0F, ctypes.sizeof(_LineValues))
ATTR_ID_OUTPUT_VALUES = 2


class Output:
    """One output line, starting low (the display BEEP input: high = buzzer on). set(0/1); close() releases it as input."""

    def __init__(self, offset, consumer="ender-loop", chip=CHIP):
        req = _LineRequest()
        req.offsets[0] = offset
        req.num_lines = 1
        req.consumer = consumer.encode()[:31]
        req.config.flags = FLAG_OUTPUT
        req.config.num_attrs = 1
        req.config.attrs[0].attr.id = ATTR_ID_OUTPUT_VALUES
        req.config.attrs[0].attr.value = 0          # low from the first instant
        req.config.attrs[0].mask = 1
        fd = os.open(chip, os.O_RDONLY)
        try:
            fcntl.ioctl(fd, GET_LINE, req)
        finally:
            os.close(fd)
        self.fd = req.fd

    def set(self, on):
        v = _LineValues(); v.mask = 1; v.bits = 1 if on else 0
        fcntl.ioctl(self.fd, LINE_SET_VALUES, v)

    def close(self):
        try:
            self.set(0)
        finally:
            os.close(self.fd)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
