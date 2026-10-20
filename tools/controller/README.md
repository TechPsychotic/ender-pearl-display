# Ender Pearl Display: desktop controller

Live mirror and knob, a no-code screen designer (live on the printer), flashing, a raw-command bench and service control
for the printer's display, from your PC.
See [docs/08-controller.md](../../docs/08-controller.md).

```bash
python3 ender_pearl_controller.py     # or ./install.sh for an app-list entry
```

| File | |
|---|---|
| `ender_pearl_controller.py` | the app (GTK 4 / libadwaita): Live, Flash, Bench, Service |
| `pi.py` | the connection: SSH with a shared control connection, the web API, finding the Pi by MAC address |
| `designer.py` | the screen designer's model: elements, the Pi canvas recording TJC instructions, checks, templates, export |
| `design_page.py` | the Design tab |
| `mirror.py` | rebuilds the screen from the display's recorded TJC commands (Pillow) |
| `install.sh` | desktop launcher + icon for this user |

`EPC_SNAPSHOT=out.png,<page>,<seconds>` saves a screenshot of the window and quits (used for the docs).
