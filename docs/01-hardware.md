# Hardware: the display, its pinout, and wiring it to a Raspberry Pi 4

## The display
| | |
|---|---|
| Module | TJC (Taojin Chi, the Chinese Nextion brand) **TJC3224T132_011N_P04**, Creality-customised |
| Panel | 320 × 240, used in portrait as **240 × 320** |
| Input | rotary knob (quadrature A/B) with push button, wired straight through the display's header |
| Flash | 8 MB (reported by the display: `comok …,8388608`) |
| Runtime version | 37 with Creality's firmware, 68 after a build with USART HMI 1.68.1 |
| Stock link | TTL UART **115200 8N1**. On the mainboard: USART2, PA2 (TX) / PA3 (RX) |
| Card slot | microSD on the display board (Creality's update route: `TJC_SET/tjc.tft`) |

## Display header
2 × 5 pins, 2.54 mm pitch, on the back of the display board. Labels as printed on the board:

|            | 1          | 2 | 3       | 4      | 5  |
|------------|------------|---|---------|--------|----|
| **top**    | GND        | B | ENTER   | RX     | NC |
| **bottom** | VCC (5 V)  | A | BEEP    | TX     | NC |

- **RX / TX** are the display's: the host's TX goes to the display's **RX**.
- **A, B, ENTER** are plain switches to GND. The mainboard reads them with its internal pull-ups (in Klipper terms
  `encoder_pins: ^PA12, ^PA11`, `click_pin: ^!PB1`), so any host with pull-ups can read them.
- **BEEP** is an input to the display board, which the mainboard drives high to beep.

### Measured levels (multimeter, DC)
| Signal | Reading | Meaning |
|---|---|---|
| VCC | ≈ 5 V | the display needs 5 V |
| A / B / ENTER at rest | 3.14 V | the mainboard's 3.3 V pull-ups; ENTER pressed ≈ 0 V |
| Display TX, idle, display powered from the Pi | **3.34 V** | 3.3 V logic: safe for a Pi GPIO directly |
| Display TX, on the mainboard | ≈ 1.5 V | a meter averaging live traffic; inconclusive, re-measured on the bench |
| BEEP idle | 0 V | |

**BEEP finding:** a Pi GPIO driving the display's BEEP pin made no sound. That covered steady high, a
300 Hz–6 kHz sweep and clicks. Neither did the mainboard's own `M300`, which puts 3.26 V on the line. On this unit
the display's buzzer is missing or dead. There is also a 10 kΩ pull-down on the display side. If you want sound,
put a 3.3 V *active* buzzer module on a Pi GPIO instead.

## Wiring to the Pi
Printer **off** while wiring. Unplug the ribbon from the display and run female–female jumpers from the display's
header to the Pi's 40-pin header. The printer keeps working over USB from the Pi. Plugging the ribbon back in
restores the original setup.

| Display | Pi pin | Pi signal | Notes |
|---|---|---|---|
| VCC 5 V | 2 | 5 V | |
| GND | 6 | GND | |
| RX | 7 | GPIO4 = **TXD3** | Pi → display |
| TX | 29 | GPIO5 = **RXD3** | display → Pi (3.3 V, measured) |
| A | 35 | GPIO19 | internal pull-up |
| B | 37 | GPIO26 | internal pull-up |
| ENTER | 33 | GPIO13 | internal pull-up, 0 = pressed |
| BEEP | 32 | GPIO12 | optional, see above |

Pin numbers are the physical header positions (odd pins in one column, even pins in the other, pin 1 = 3V3).
Seven wires go to the first and last few rows of the header: power and RX near pin 1, the rest at pins 29–37.

**Send-only bench test:** to draw you only need Pi TX → display RX. You can leave the display's TX unconnected
until you've measured it.

## Pi configuration
- **Use UART3, not the primary UART.** On a stock Pi OS / Ubuntu image the primary UART carries the login
  console (`console=serial0,115200`, `serial-getty@ttyS0`). The mini UART's baud rate also follows the CPU
  clock. The Pi 4 has spare PL011 UARTs:
  ```
  # /boot/firmware/config.txt
  dtoverlay=uart3        # GPIO4 = TXD3 (pin 7), GPIO5 = RXD3 (pin 29) -> /dev/ttyAMA3 here
  ```
  `pi/display/link.py` finds the right `/dev/ttyAMA*` by UART3's device-tree address (`7e201600`), so it doesn't
  matter which number the kernel gives it.
- **Knob:** no GPIO Python package is needed. `pi/display/gpio.py` talks to the kernel's GPIO character device
  (uAPI v2) with the standard library only: inputs with pull-up, both-edge events and the kernel's 1 ms debounce.
  `gpio.Quadrature` decodes the knob (4 steps per detent, ignores impossible jumps). A press held for 0.8 s means
  "back".
- **Free GPIOs** used here: 4, 5, 12, 13, 19, 26. GPIO 7/8 belong to SPI; GPIO 14/15 are the console UART.

## Safety notes
- Never connect a 5 V signal to a Pi GPIO. Measure first (every line here measured ≤ 3.4 V).
- The Pi's 5 V pin powers the display directly. The display draws little, but use a proper Pi power supply.
- Plugging the display back onto the mainboard with *our* firmware on it gives a blank or confused screen,
  because the mainboard speaks Creality's protocol. Restore the stock firmware first if you go back to stock
  wiring ([docs/03](03-custom-firmware.md#back-to-stock)).
