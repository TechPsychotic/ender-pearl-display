"""First test of OUR display firmware: draw with the Pi using TJC instructions (font 0 = Inter 24)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serial
import link, tjc
import protocol as D

s = serial.Serial(link.find_port(), 115200, timeout=0.3)
s.reset_input_buffer()
s.write(tjc.replies(True)); time.sleep(0.1)
BG, ACC = D.rgb565(16, 18, 22), D.rgb565(34, 197, 94)
s.write(tjc.cls(BG))
s.write(tjc.fill(0, 0, 240, 36, D.rgb565(40, 44, 52)))
s.write(tjc.text(10, 0, 220, 36, "Ender Loop", 0, D.WHITE, align=tjc.LEFT))
s.write(tjc.text(10, 60, 220, 30, "Our own firmware", 0, ACC))
s.write(tjc.text(10, 100, 220, 30, "Nozzle  195 / 195 C", 0, D.WHITE))
s.write(tjc.text(10, 135, 220, 30, "Bed      55 / 55 C", 0, D.WHITE))
s.write(tjc.circle(120, 240, 40, ACC))
s.write(tjc.fill(20, 300, 200, 6, D.rgb565(60, 64, 72))); s.write(tjc.fill(20, 300, 130, 6, ACC))
time.sleep(0.4)
print("replies:", tjc.parse_replies(s.read(400)))
