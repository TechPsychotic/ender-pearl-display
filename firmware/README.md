# Firmware

| File | sha256 | What |
|---|---|---|
| `glass.tft` | `9e6abf0bb2c5e1f64695aea054759d3ed26da7ea796c5d429aec9556d9758bcb` | the Ender Pearl glass firmware for the **TJC3224T132_011N** (Ender-3 V3 SE display), the exact build running on our printer |
| `glass.hmi` | `4301ff193c92be30dac6effc1e40220027e87b6202a637c7c400e772a6cc103b` | its TJC USART HMI 1.68.1 project: one blank page, 7 fonts, the wallpaper and boot pictures |

Flash from the Pi (see [docs/03-custom-firmware.md](../docs/03-custom-firmware.md)):

```bash
python3 pi/display/flash.py --probe              # must report TJC3224T132_011N
python3 pi/display/flash.py firmware/glass.tft
```

Picture and font ids in this build are listed in `design/assets/manifest.json` (copied to `pi/display/glass/manifest.json`).
Rebuild the `.tft` whenever pictures or fonts change, and keep the manifest in step with it.

**Only for the TJC3224T132_011N.** Back to Creality's firmware: [docs/03-custom-firmware.md#back-to-stock](../docs/03-custom-firmware.md#back-to-stock).
