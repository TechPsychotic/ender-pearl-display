# TJC USART HMI editor on Linux

TJC's editor is Windows-only (and its own code is encrypted, so it can't be ported). It runs under Wine.
These scripts let you run it and drive it from Python.

## Setup
```bash
export WINEPREFIX=~/.wine-tjc
winetricks -q dotnet35sp1 dotnet48 corefonts     # the editor's loader needs the .NET 2.0 runtime (in 3.5 SP1)
wine USARTHMIsetup_1.68.1.exe                    # TJC's installer (tjc1688.com), not included here
./run-editor.sh
```

For scripting, unzip the **Windows embeddable Python** (python.org, "embeddable package") into `winpy/`, next to
`winside.py`. Our input runs inside Wine because GNOME blocks synthetic X input to XWayland windows. `xdrive.py`
also needs `python3-xlib` on the Linux side.

| Script | |
|---|---|
| `run-editor.sh` | start the editor in its prefix |
| `tjcui.py` | `shot out.png`, `click X Y [right\|double]`, `text "…"`, `key esc ctrl+s …`. Coordinates are relative to the editor window |
| `winpy/winside.py` | the Windows side: `SendInput`, window and child-control lists, select by handle |
| `xdrive.py` | screenshots of the Wine windows (dialogs too), window list |
| `gen_fonts.py` | generate the 7 fonts with the editor's font tool and add them to the project, in id order |
| `import_pics.py <first> [last]` | import `design/assets` pictures into the open project, in manifest order |

The editor's interface is in Chinese. The scripts find controls by handle and window size, not by label.
