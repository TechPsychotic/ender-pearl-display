#!/bin/bash
# TJC USART HMI editor (1.68.1) under Wine, in its own prefix (~/.wine-tjc: .NET 4.8 + core fonts).
export WINEPREFIX="$HOME/.wine-tjc" WINEDEBUG=-all
cd "$WINEPREFIX/drive_c/Program Files (x86)/USART HMI" || exit 1
exec wine "USART HMI.exe" "$@"
