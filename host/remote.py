"""Host-side control for the IR transmitter (Arduino Uno or ESP32 firmware).

  python remote.py key power                 named key on the normal device code
  python remote.py send 41 47 --frames 3     raw Emerson device/function
  python remote.py factory 8                 service-remote format (J1 linked), e.g. 8 = H-P
  python remote.py nec 0xE084 0x20           NECext frame (newer Funai LCD sets)
  python remote.py selftest                  send a frame and check the receiver decodes it
  python remote.py listen                    print/decode IR seen by the receiver
  python remote.py sweep                     Phase 2 device-code sweep (resumable)

The serial port is auto-detected; override with --port or EMERSON_PORT.
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import serial
from serial.tools import list_ports

import emerson

HERE = Path(__file__).resolve().parent
STATE_FILE = HERE / "sweep_state.json"
LOG_FILE = HERE / "sweep_log.csv"
BOARD_USB_VIDS = {0x2341, 0x2A03, 0x10C4, 0x1A86, 0x303A, 0x0403}  # Arduino, CP210x, CH340, Espressif, FTDI


def find_port():
    ports = [p for p in list_ports.comports() if p.vid in BOARD_USB_VIDS]
    if len(ports) == 1:
        return ports[0].device
    found = ", ".join(p.device for p in list_ports.comports()) or "none"
    sys.exit(f"Can't pick a serial port automatically (found: {found}). Use --port.")


class Transmitter:
    def __init__(self, port):
        self.ser = serial.Serial(port, 115200, timeout=0.2)
        # Opening the port resets the Uno and most ESP32 boards; wait for the banner, then ping.
        deadline = time.time() + 4
        while time.time() < deadline:
            if self.ser.readline().decode(errors="replace").startswith("READY"):
                break
        self.command("PING")

    def command(self, line, timeout=5):
        self.ser.write((line + "\n").encode())
        deadline = time.time() + timeout
        while time.time() < deadline:
            reply = self.ser.readline().decode(errors="replace").strip()
            if reply.startswith("OK"):
                return reply
            if reply.startswith("ERR"):
                raise RuntimeError(f"{line!r}: {reply}")
        raise TimeoutError(f"no reply to {line!r}")

    def emerson(self, device, function, frames=2):
        return self.command(f"E {device} {function} {frames}", timeout=2 + frames * 0.2)  # a frame takes up to 125 ms

    def factory(self, device, function, frames=2):
        """Service-remote format, sent as raw timings so the firmware needs no change."""
        timings = " ".join(map(str, emerson.encode(device, function, factory=True)[:-1]))
        for _ in range(frames):
            self.command(f"R 36700 {timings}")
            time.sleep(0.034)  # 39-unit gap between frames
        return f"OK factory {device} {function} x{frames}"

    def readline(self):
        return self.ser.readline().decode(errors="replace").strip()


def parse_int(text):
    return int(text, 0)


def resolve_function(text):
    return emerson.KEYS[text.lower()] if text.lower() in emerson.KEYS else parse_int(text)


def device_order(base):
    """Base device's single-bit flips first (most likely what the J1/J2 jumper does),
    then two-bit flips, then everything else. The base device itself is excluded."""
    def rank(d):
        flips = bin(d ^ base).count("1")
        return (flips if flips <= 2 else 3, d)
    return sorted((d for d in range(64) if d != base), key=rank)


class Keys:
    """Non-blocking single-key reads (Windows console, or POSIX terminal)."""

    def __init__(self):
        if os.name == "nt":
            import msvcrt
            self._msvcrt = msvcrt
        else:
            import termios
            import tty
            self._fd = sys.stdin.fileno()
            self._old = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)

    def get(self):
        if os.name == "nt":
            return self._msvcrt.getwch().lower() if self._msvcrt.kbhit() else None
        import select
        if select.select([sys.stdin], [], [], 0)[0]:
            return sys.stdin.read(1).lower()
        return None

    def close(self):
        if os.name != "nt":
            import termios
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)


def log_event(index, device, function, event):
    new = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "index", "device", "function", "event"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), index, device, function, event])


def cmd_sweep(tx, args):
    if args.functions == "unknown":
        functions = [f for f in range(64) if f not in emerson.KEYS.values()]
    else:
        functions = [resolve_function(f) for f in args.functions.split(",")]
    if args.devices:
        devices = [parse_int(d) for d in args.devices.split(",")]
    else:
        devices = device_order(args.base)
    if args.base in devices and any(f not in (emerson.KEYS["menu"], emerson.KEYS["display"], emerson.KEYS["sleep"]) for f in functions):
        print("warning: sweeping other functions on the normal device code can trigger real TV functions")
    plan = [[d, f] for d in devices for f in functions]  # lists, so it compares equal after a JSON round trip
    config = {"plan": plan, "frames": args.frames, "delay": args.delay}

    index = 0
    if STATE_FILE.exists() and not args.restart:
        state = json.loads(STATE_FILE.read_text())
        if state["config"] == config:
            index = state["index"]
            print(f"resuming at step {index + 1}/{len(plan)} (use --restart to start over)")
        else:
            sys.exit("sweep_state.json is from a sweep with different settings; use --restart to discard it")

    def save():
        STATE_FILE.write_text(json.dumps({"config": config, "index": index}))

    print(f"{len(plan)} steps, {args.delay}s apart. Keys: [p] pause/resume  [h] HIT - stop, something appeared  [q] quit")
    keys = Keys()
    paused, recent, pending = False, [], None
    try:
        while index < len(plan):
            key, pending = pending or keys.get(), None
            if key == "q":
                log_event(index, "", "", "quit")
                print("\nquit; progress saved, run sweep again to resume")
                return
            if key == "h":
                log_event(index, "", "", "hit")
                print("\nHIT. Most recent frames, newest first (the TV may lag a step or two):")
                for i, d, f in reversed(recent):
                    print(f"  step {i + 1}: device {d} function {f}   ->  python remote.py send {d} {f}")
                print("Re-send each one individually to find which one opened the service screen.")
                # Back the index up so a resume revisits the suspects.
                if recent:
                    index = recent[0][0]
                return
            if key == "p":
                paused = not paused
                log_event(index, "", "", "paused" if paused else "resumed")
                print("\npaused - [p] to resume" if paused else "\nresumed")
            if paused:
                time.sleep(0.1)
                continue

            device, function = plan[index]
            tx.emerson(device, function, args.frames)
            log_event(index, device, function, "sent")
            recent = (recent + [(index, device, function)])[-3:]
            print(f"\r[{index + 1}/{len(plan)}] device {device:2d} function {function:2d}   ", end="", flush=True)
            index += 1
            save()

            wait_until = time.time() + args.delay
            while time.time() < wait_until:
                time.sleep(0.05)
                pending = keys.get()
                if pending:
                    break
        print("\nsweep finished with no hit logged")
    finally:
        save()
        keys.close()


def cmd_selftest(tx, attempts=5):
    """Send MENU and look for it on the receiver. A single process has to do both,
    because only one program at a time can hold the serial port."""
    device, function = emerson.DEFAULT_DEVICE, emerson.KEYS["menu"]
    tx.command("L 1")
    seen_other = 0
    for _ in range(attempts):
        tx.emerson(device, function)
        deadline = time.time() + 1
        while time.time() < deadline:
            line = tx.readline()
            if not line.startswith("RAW"):
                continue
            decoded = emerson.decode([int(x) for x in line.split()[1:]])
            if decoded == (device, function):
                print(f"PASS: receiver decoded device {device} function {function}")
                return True
            seen_other += 1
    if seen_other:
        print(f"FAIL: receiver saw IR {seen_other} time(s) but it didn't decode to the frame sent. "
              "Try more distance between the LED and receiver.")
    else:
        print("FAIL: receiver saw nothing. Check the LED polarity and wiring, and that the LED faces the receiver.")
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", default=os.environ.get("EMERSON_PORT"))
    sub = p.add_subparsers(dest="cmd", required=True)

    k = sub.add_parser("key", help="send a named key: " + " ".join(emerson.KEYS))
    k.add_argument("name", choices=list(emerson.KEYS))
    k.add_argument("--device", type=parse_int, default=emerson.DEFAULT_DEVICE)
    k.add_argument("--frames", type=int, default=2)

    s = sub.add_parser("send", help="send an Emerson device/function frame")
    s.add_argument("device", type=parse_int)
    s.add_argument("function", type=resolve_function, help="0-63 or a key name")
    s.add_argument("--frames", type=int, default=2)

    fk = sub.add_parser("factory", help="send in the service remote's format (J1 linked): 8, 9, ch+, ch- ...")
    fk.add_argument("function", type=resolve_function, help="0-63 or a key name")
    fk.add_argument("--device", type=parse_int, default=emerson.DEFAULT_DEVICE)
    fk.add_argument("--frames", type=int, default=2)

    n = sub.add_parser("nec", help="send an NEC/NECext frame")
    n.add_argument("address", type=parse_int)
    n.add_argument("command", type=parse_int)
    n.add_argument("--repeats", type=int, default=0)

    sub.add_parser("selftest", help="send a frame and check the board's own receiver decodes it")
    sub.add_parser("listen", help="print IR captured by the receiver (Ctrl+C to stop)")

    w = sub.add_parser("sweep", help="step through device codes looking for service mode")
    w.add_argument("--base", type=parse_int, default=emerson.DEFAULT_DEVICE, help="normal device code")
    w.add_argument("--devices", help="explicit comma-separated device list (default: all 64, likely first)")
    w.add_argument("--functions", default="sleep", help="comma-separated functions/key names to send per device, or 'unknown' for every function with no known key")
    w.add_argument("--frames", type=int, default=3)
    w.add_argument("--delay", type=float, default=1.5, help="seconds to wait after each send")
    w.add_argument("--restart", action="store_true", help="discard saved progress")

    args = p.parse_args()
    tx = Transmitter(args.port or find_port())

    if args.cmd == "key":
        print(tx.emerson(args.device, emerson.KEYS[args.name], args.frames))
    elif args.cmd == "send":
        print(tx.emerson(args.device, args.function, args.frames))
    elif args.cmd == "factory":
        print(tx.factory(args.device, args.function, args.frames))
    elif args.cmd == "nec":
        print(tx.command(f"N {args.address} {args.command} {args.repeats}"))
    elif args.cmd == "selftest":
        sys.exit(0 if cmd_selftest(tx) else 1)
    elif args.cmd == "listen":
        tx.command("L 1")
        print("listening; point a remote at the receiver (Ctrl+C to stop)")
        try:
            while True:
                line = tx.readline()
                if not line.startswith("RAW"):
                    continue
                timings = [int(x) for x in line.split()[1:]]
                decoded = emerson.decode(timings)
                factory = emerson.decode(timings, factory=True)
                if decoded:
                    print(f"Emerson device {decoded[0]} function {decoded[1]}")
                elif factory:
                    print(f"FACTORY device {factory[0]} function {factory[1]}")
                else:
                    print(f"unknown ({len(timings)} timings): {' '.join(map(str, timings))}")
        except KeyboardInterrupt:
            pass
    elif args.cmd == "sweep":
        cmd_sweep(tx, args)


if __name__ == "__main__":
    main()
