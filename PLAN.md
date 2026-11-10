# DIY IR Service Remote for Emerson EWF2004A CRT

> The original plan, kept for the record. What actually worked is in [README.md](README.md) and [NOTES.md](NOTES.md).

## Goal
Build a DIY IR transmitter that gets an Emerson EWF2004A 20" CRT TV into its factory/service mode so the picture geometry (H/V position, size, linearity) can be corrected. The TV has no remote.

## Background
- **TV:** Emerson EWF2004A, 20" flat-screen SD CRT, made by Funai (~2005). Sibling models: EWF2004, EWF2006/EWF2006A.
- **Problem:** Picture alignment is off. Geometry is only adjustable in service mode.
- **How service mode is normally reached:** On the EWF2004, the original remote is modified by desoldering the jumper at J1 and moving it to J2 on the remote PCB, turning it into a factory/service remote.
  - Source: https://shmups.system11.org/viewtopic.php?p=1583556
- **Working hypothesis:** On Funai remotes, that jumper most likely changes the device/address (custom) code the remote sends, while button command codes stay the same. If so, factory mode = normal commands sent with a different device code, which is a small search space.
- **IR protocol:** Funai/Emerson TVs use an Emerson-style protocol (carrier roughly 36–38 kHz). The JP1 community at hifi-remote.com knows it well (look for the "Emerson" protocols and Funai threads).
- **Service manual:** EWF2004 service manual (52 pages, free): https://elektrotanya.com/emerson_ewf2004.pdf/download.html. It covers menu items and service mode entry/exit.
- **Existing hardware in the household:** Home Assistant setup. The hardware choice below is still open.

## Hardware (pick one)
1. **ESP32 + IR LED + NPN transistor (e.g. 2N2222) + resistor** (preferred: cheap, scriptable, easy to sweep codes)
   - Library: IRremoteESP8266 (Arduino/PlatformIO), or ESPHome `remote_transmitter` integrated with Home Assistant.
   - Optional: TSOP38238 IR receiver for capturing/verifying codes from any Funai remote later.
2. **Flipper Zero:** can load IRDB `.ir` files directly; good for steps 1–2, clunkier for sweeping.
3. **Broadlink RM via Home Assistant:** sends raw or Pronto codes; usable but less control over protocol encoding.

## Phase 1: Prove basic control
1. Find known Emerson/Funai TV codes:
   - Flipper IRDB (GitHub: Lucaslhm/Flipper-IRDB), under TVs → Emerson / Funai / Sylvania / Symphonic
   - LIRC remotes database (Funai/Emerson entries)
   - hifi-remote.com (JP1) for setup codes and protocol details
2. Determine the protocol and its parameters: carrier frequency, timings, device code, command codes.
3. Implement the transmitter and confirm basic commands work: POWER, VOL+/-, CH+/-, MENU, input select.
4. **Exit criterion:** the TV reliably responds to normal commands. This proves the protocol, timing, and transmitter are right. Do not proceed to Phase 2 until this works.

## Phase 2: Find the factory/service mode
1. **Ask first:** post on hifi-remote.com forums asking for the Funai factory/service device code for EWF2004 / Funai CRT chassis of that era. Someone may already know it.
2. **If unknown, sweep:**
   - Keep the command byte fixed to a harmless key (MENU or DISPLAY).
   - Step through alternative device/address codes. Start with values adjacent to or a bit-flip from the normal device code (likely what the jumper does), then widen.
   - Send each code a few times, pause ~1–2 s, and log which code was sent.
   - Watch the TV for a service/factory screen. A webcam plus manual observation is fine. Alternatively, pause between batches and have the user confirm.
   - **Stop immediately** when a service screen appears and record the exact code.
3. Avoid sweeping command codes randomly with the normal device code. That can trigger unintended functions.

## Phase 3: Adjust geometry
1. Read the relevant service-mode section of the EWF2004 service manual first.
2. **Before changing anything, photograph or write down every original value.**
3. Adjust one item at a time: H position, V position, H size, V size, linearity. Leave white balance, cutoff, and other non-geometry settings alone.
4. Use a test pattern from the actual source (NES, via the composite input) since that's what the TV is for. 240p Test Suite on a flash cart is ideal if available.
5. Exit service mode as described in the manual so values are saved.

## Deliverables
- Transmitter firmware/config (ESPHome YAML or Arduino sketch) that can send:
  - normal Emerson/Funai TV commands
  - parameterized protocol frames (device code + command) for the sweep
- Sweep script with logging, which is pausable and resumable, and can stop on user signal
- Notes file: confirmed protocol parameters, normal device code, discovered factory code, original service-mode values, final adjusted values

## Safety
- Never open the TV. The CRT holds a dangerous charge even when unplugged. All adjustments are done through service mode only.
- Keep a record of original service values so everything can be restored.

## Fallbacks
- If Phase 1 works but Phase 2 dead-ends: buy an original Funai/Emerson remote (search terms: `Emerson NE147UD remote`, `Emerson EWF2004 remote control original`, `Emerson NE128UD`) and do the J1→J2 jumper mod. A captured factory signal from that remote could also be replayed by the DIY transmitter.
- If the image is only tilted/rotated: try rotating the TV's orientation, moving it away from speakers or magnets, and power-cycling after 20+ minutes off to degauss before entering service mode.
