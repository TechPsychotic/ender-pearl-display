"""Serial link to the TJC3224 display wired to the Pi (DISPLAY_RE.md plan B). 115200 8N1: the stock firmware and
jpcurti's Klipper module both use 115200 on the mainboard's USART2.

Default port: the Pi 4's PL011 UART3 (dtoverlay=uart3: GPIO4 = TXD3 on pin 7, GPIO5 = RXD3 on pin 29), found by
its device-tree address, so the mini UART on pins 8/10 (Linux console, CPU-clock dependent baud) stays out of it."""
import glob
import os
import time

import serial

import protocol as D

BAUD = 115200
UART_ADDR = {"uart3": "7e201600", "uart2": "7e201400", "uart4": "7e201800", "uart5": "7e201a00", "uart0": "7e201000"}


def find_port(uart="uart3"):
    for dev in sorted(glob.glob("/sys/class/tty/ttyAMA*")):
        try:
            node = os.path.realpath(os.path.join(dev, "device", "of_node"))
        except OSError:
            continue
        if UART_ADDR[uart] in node:
            return "/dev/" + os.path.basename(dev)
    return None


class Display:
    def __init__(self, port=None, baud=BAUD, pace=0.002):
        port = port or find_port()
        if not port:
            raise RuntimeError("no UART3 found: add dtoverlay=uart3 to /boot/firmware/config.txt and reboot (see DISPLAY_RE.md)")
        self.port, self.pace = port, pace
        self.ser = serial.Serial(port, baud, timeout=0.05)

    def send(self, *frames):
        for f in frames:
            self.ser.write(f)
            if self.pace:
                time.sleep(self.pace)   # the display has a small input buffer; jpcurti waits 1 ms per frame

    def handshake(self, tries=10):
        """True once the display answers OK. Safe test of the wiring: draws nothing."""
        for _ in range(tries):
            self.ser.reset_input_buffer()
            self.ser.write(D.handshake())
            time.sleep(0.12)
            if D.is_handshake_reply(self.ser.read(64)):
                return True
        return False

    def send_only_init(self):
        """Display TX not wired: send the handshake the way the stock firmware does at boot (AA 00, then AA 3D) and go on.
        Drawing needs only Pi TX → display RX."""
        for _ in range(3):
            self.ser.write(D.handshake())
            time.sleep(0.12)
        self.send(D.frame(0x3D))
        time.sleep(0.1)

    def close(self):
        self.ser.close()
