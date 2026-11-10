# Notes

> Working log, newest findings near the bottom. Photos referenced as `photos/...` are not all published; the key ones are in `docs/images/`.

## Protocol (from research, 2026-10-24; confirmed on the EWF2004A 2026-11-01)

Funai CRTs of this era use the JP1 **"Emerson"** protocol:

```
{36.7k,872}<1,-1|1,-3>(4,-4,D:6,F:6,~D:6,~F:6,1,-39)+
```

- Carrier is 36.7 kHz and the time unit is 872 µs. The header is a 4-unit mark followed by a 4-unit space.
- Each bit is a 1-unit mark. A 0 bit has a 1-unit space and a 1 bit has a 3-unit space.
- The 24 bits are sent LSB-first: 6-bit device, 6-bit function, then the complement of each.
- Because the device code is only 6 bits, there are just 64 device codes, so the full sweep is small.

Source: Symphonic ST424FF (a Funai CRT) raw capture in Flipper-IRDB, copied to
`reference/Symphonic_ST424FF.ir`. All 22 buttons decode cleanly to **device 41**, and
`host/test_emerson.py` checks that the encoder reproduces those captures exactly.

| Key | F | Key | F | Key | F |
|---|---|---|---|---|---|
| power | 32 | menu | 47 | 1–9 | 31, 33–40 |
| vol+ / vol- | 48 / 49 | select | 46 | 0 | 41 |
| ch+ / ch- | 16 / 8 | display | 15 | set+ / set- | 6 / 7 |
| mute | 51 | input | 13 | | |

### Related leads
- Newer Funai LCD sets (for example the Emerson LF501EM4) use **NECext with address bytes 84 E0**
  (`nec 0xE084 <cmd>`). Funai's NF021RD LCD remote in LIRC
  (`reference/Funai_NF021RD.lircd.conf`) has a hidden `SERVICE` key, NEC
  command **0xFF** on that address. That's a different protocol from this CRT, but it suggests
  Funai uses a dedicated "service" function code instead of, or alongside, a separate device code.
  If the device sweep finds nothing, sweeping functions on the most likely device codes is the next thing to try.

## Phase 1 results
- Normal device code confirmed: **41** (TV showed its volume bar for device 41, function 48, on 2026-11-01)
- Keys that work: vol+, vol-, menu, sleep confirmed. Others: _
- Range / LED setup: Uno on D3, PN2222, 51 Ω from 5 V, about 3 ft. `selftest` passes.

## Phase 2 results
- 2026-11-01: full sweep of MENU (F47) on the 63 other device codes: no visible change.
- Service manual for the sibling 27" 6427FD/EWF2703 (p. 5-1), found 2026-11-01:
  - Service remote = normal remote (N0138UD/N0139UD) with jumper J1 added.
  - Enter: main power on at the TV, press **SLEEP** on the service remote. The microcomputer version appears (e.g. 054-0.05).
  - Geometry: **8** = H-P; **9** cycles V-S / V-P; **CH up/down** changes the value. Warm up 20+ min first.
  - Save/exit: main power off and on at the TV.
  - Number keys also open non-geometry items (6 = B-S, 3 = U/V pedestal, 1 = SD check/factory mode), and the lower-left value (2812 on that model) is an initial setting. Don't touch those.
  - That manual is for the 27"; check against the EWF2004 manual, whose key assignments may differ.
- SLEEP is function 11 on device 41 (`reference/Symphonic_TV_41.csv`, from probonopd/irdb).
- 2026-11-01: full sweep of SLEEP (F11) on the 63 other device codes: no visible change. So J1 probably doesn't just change the device code. Next hypothesis: J1 changes the function code, so try the unassigned functions on device 41.
- 2026-11-01: **service mode reached** at the end of the unassigned-function sweep on device 41 (`--devices 41 --functions unknown`).
- Factory/service code: **device 41, function 63** (`python remote.py send 41 63 --frames 3`), confirmed on its own 2026-11-01.
- Service screen (`photos/service-mode-entry-screen.jpg`): `058-0.06 271 A1` at top, `0F` over `2641` lower left, a `2` near each corner.
- In service mode, normal 8 (F39) and MENU (F47) on device 41 did nothing visible. A re-send of F63 also showed no change. Key 8 on the 63 other device codes, also in service mode, showed nothing.
- 2026-11-01, webcam-checked (`host/scan.py`, `host/watch.py`): LED aim confirmed by VOL- in normal mode, and F63 re-entered service mode. From the version screen, the 40 other unassigned functions on device 41 caused no visible change (largest difference 0.50%, background reflections), and the end frame still read `0F`, `2641`. Normal VOL- also did nothing with `SHARP` showing.
- Conclusion so far: in service mode the TV ignores every device-41 code tried except what opens it, including codes that act in normal mode (the channel and video/game ones). Front-panel MENU and VOL still work there.
- 2026-11-01, full scan from the version screen (`host/scan.py`, log in `host/scan_log.csv`): 4,094 of 4,096 device/function pairs, 3 frames each, no reaction. Not sent: device 41 POWER and F63. Stops at d3 f24, d21 f47/f54/f58 and d34 f63 were camera movement or refocus, not the TV. LED aim not yet re-confirmed after the camera moved.
- 2026-11-01, after the full scan: VOL- in normal mode still showed the volume bar and F63 still opened service mode, so the LED is aimed now. `host/press_test.py` sent 8, 9 (1 and 50 frames) and CH up/down (1 and 10 frames) from the version screen and again after front-panel MENU: no reaction (peak 18 of 600).
- Service remote notes: 6420FE manual p. 5-1 (ManualsLib p. 15). Lists NE154UD, N0132UD, NE116UD, NE122UD, NE121UD for the EWF2004; add jumper J1.
- Other functions seen on device 41, not identified: one of 10/12/14 changes the channel; one of 50/52/53 changed video to game mode.

## Research, 2026-11-01
No published code or DIY success found for this chassis. Reddit, shmups.system11.org and JustAnswer block fetching, so those were only read as search summaries.
- JustAnswer (ILO/Funai IWF2706 thread, summary only): J1 joins the SLEEP contact to the DTV/TV button trace. If so, J1 may only change SLEEP, and service-remote 8 and 9 would be the normal codes the TV is ignoring. Inference: F63 may open the screen without the state where IR works.
- Untested from normal mode: other devices with functions besides F11 and F47. The full scan ran from the service screen, where a second entry code might show no visible change. This is the best next scan.
- ILO IWT3206 manual (similar J1/SLEEP procedure): INFO changes the four corner indicators. DISPLAY (F15) did nothing here, which fits the same idea, but it's a different chassis.
- hifi-remote EWL20S5 thread: suggests unused function codes and warns some only respond in a certain state; never found a working code. Also describes Power + Sleep to enter (unverified, other model).
- A search summary of a JP1 thread lists TV/0180 as NECx1 device 8.8 alongside Emerson 41; the thread itself wasn't found. Cheap test: 256 commands at NEC address 0x0808.

- Read via screenshots, 2026-11-02:
  - r/crt "Emerson requiring you to make your own service remote" (u/vascohaddon): made one; the jumpered remote "controls the service menu, but not the TV". So J1 changes every key, not just SLEEP. No codes posted. No tilt/convergence in service mode (convergence is magnets/yoke inside).
  - JustAnswer IWF2706 (NE906UD remote): J1 location was given from memory (SLEEP-contact corner pin to DTV/TV trace); the customer said it didn't work. Weak.
  - electronics-lab, Sylvania 6427TD: vertical size is in the service menu, horizontal width is pot VR562 on the TV board. This manual also lists only H-P, V-S, V-P, so width is probably a board pot here too (inside the TV: not doing that).

### Tests from the research, 2026-11-02 (TV moved; webcam detector now BRIGHT 220, 5x5 erosion, fresh reference per code)
- F63 sent every second until the TV came on, so service mode opened within about a second of main power: 8, 9 (1 and 50 frames) and CH up/down (1 and 10 frames) still did nothing.
- F63 followed immediately by each device-41 function except POWER: no reaction.
- NEC address 0x0808, all 256 commands, from the version screen: no reaction.
- All 4,032 codes on the 63 other devices from normal mode (`scan.py --log scan_normal_log.csv --keep-going`): no way into service mode. 31 flags, all reflections of people moving; the TV still showed only `VIDEO 2` at the end, and service mode ignores those codes, so an entry would have stayed on screen.
- Conclusion: every standard-format code is covered from both states. The service remote must send a different format. Next step: buy an original remote (NE116UD family), record it normal and jumpered with the receiver, replay from the Uno.
- The user's actual problem (photo 2026-11-02): the top-right corner runs off the glass, other edges have a margin. Degauss, moving magnets and turning the TV didn't help. Plan: H-P left and V-P down one step at a time; if another corner cuts off first, it's corner geometry and can't be fixed from outside.

## Original remote (N0132UD/NE142UD listing, eBay), arrived 2026-11-09
- Works the TV (volume). Recorded unmodified with `remote.py listen`, all standard Emerson format, device 41:
  SLEEP 11, 8 = 39, 9 = 40, CH up 16, CH down 8, MENU 47, VOL down 49, **CHANNEL RETURN 14**, DISPLAY 15.
- Opened it (`photos/remote-board-*.jpg`). Board BN0113F01011, silkscreen "L10 NTSC W/FACTORY". Printed table: **J1 open = NORMAL, J1 = JW5.0 (5 mm wire link) = FACTORY**. J1 is two empty holes beside IC1 pin 11, near Q1, at the battery end.
- J1 linked 2026-11-09 and recorded. **SLEEP sends normal-format device 41 F63** (the code found by scanning). Every other key sends the **same function number as the normal remote, but the frame's second 12 bits repeat device+function instead of complementing them**: `{36.7k,872}<1,-1|1,-3>(4,-4,D:6,F:6,D:6,F:6,1,-39)+`. That's why scanning standard frames could never work.
- Factory frames seen: 8 = F39, 9 = F40, CH up F16, CH down F8, MENU F47, VOL down F49, CH RETURN F14, DISPLAY F15 (all device 41).
- `python remote.py factory <key>` sends this format from the Uno (raw timings, no reflash). Loopback through the Uno's own receiver decodes it as factory 41/15. `listen` now prints `FACTORY device ... function ...`.

## Service manual for this TV: Emerson 6420FE / EWF2004
https://www.manualslib.com/manual/553858/Emerson-20-Color-Television-6420fe.html (pp. 15-19)

This TV's screen matches the manual's example exactly: version 058-0.06, lower-left 2641 (the correct value, leave it).

Geometry, after 20+ min warm-up (the manual says to use a monoscope pattern):
- **8**: H-P, horizontal position.
- **9**: cycles V-S (vertical size) and V-P (vertical position).
- **CH up/down**: changes the selected value. Only press it after confirming the label on screen.
- Exit: main power button on the TV, off and on. The manual has no remote exit key.

Leave alone:
- **1** SD check, **2** H-ADJ, **3** pedestal/cut-off, **4/5** white balance, **6** black stretch, **7** purity colors.
- **VOL down** steps initial settings; **MENU** steps picture settings.
- **CH RETURN then hold 5 for 5 s**: software reset. The manual doesn't say what it erases.
- `0F` on the entry screen isn't explained in the manual.

Manual has no H-size or linearity adjustment in the sections read so far (pp. 15-19).

## Original service-mode values (photograph too)
Front-panel MENU works in service mode: it showed `BRT` in purple text, over the game picture (`photos/service-mode-brt.jpg`).

| Item | Original | Final |
|---|---|---|
| BRT | 128-o(64)+u(64) | unchanged |
| CNT | 84=o(6)+u(78) | unchanged |
| CLR | 58=o(6)+u(52) | unchanged |
| S-CLR | 58=o(6)+u(52) | unchanged |
| TNT | 60=o(28)+u(32) | unchanged |
| V-TNT | 60=o(28)+u(32) | unchanged |
| S-TNT | 60=o(28)+u(32) | unchanged |
| SHARP | 43=o(3)+u(40) | unchanged |
| S-SRP | 43=o(3)+u(40) | unchanged |

Photos: `photos/menu-*.jpg`. These match the manual's target values (CNT 84, CLR/S-CLR 58, TNT/V-TNT/S-TNT 60, SHARP/S-SRP 43). No geometry items on the front-panel MENU list.

Front-panel VOL down list (`photos/vol-*.jpg`), original values: 7F = FF; C/D = -; LANGUAGE = SPA/FRA; ACCESS CODE = OFF; SOUND TYPE = MTS; VIDEO TONE = ON; FM-MODE = OFF; V-OUT = OFF; AV MEMO = OFF; STABLE SOUND = OFF; FILTER = OFF; 1000; YUV MEMORY = OFF; NO SIG BRT 0; A-MUTE POL. = H; V-MENU = OFF.
All match the manual's targets. VIDEO = V1/V2 also confirmed (read off the screen, no photo). No geometry items on this list.

IR key 8 (F39 on device 41) still did nothing with BRT showing.
