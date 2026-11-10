"""Unattended code scan: send each code, compare webcam frames, stop at the first reaction.

  python scan.py                                      every remaining device/function pair
  python scan.py --devices 41 --functions unknown     a smaller set

Each frame is compared with a reference taken at the start, counting only bright text
pixels, so moving reflections in the glass don't count and one changed digit does.
Every step is appended to scan_log.csv, and codes already logged are skipped, so
running it again resumes. Point the webcam at the screen with the service screen up.
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

import emerson
import remote
from watch import Camera

HERE = Path(__file__).resolve().parent
LOG_FILE = HERE / "scan_log.csv"

# On the normal device code: power would leave service mode, and 63 is what opens it.
NEVER_SEND = {(emerson.DEFAULT_DEVICE, emerson.KEYS["power"]), (emerson.DEFAULT_DEVICE, 63)}

SCREEN = (0, 1000, 30, 1700)  # y1, y2, x1, x2 of the TV screen in the webcam frame; re-check if the camera moves
BRIGHT = 220  # grey level of on-screen text; 190 let reflections of a white wall through
KERNEL = np.ones((5, 5), np.uint8)  # 3x3 let exposure drift through as thicker/thinner text


def text_mask(image):
    y1, y2, x1, x2 = SCREEN
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)[y1:y2, x1:x2] > BRIGHT


def text_change(reference, image):
    """Bright pixels that differ, eroded to ignore edge shimmer and exposure drift.
    Under 70 for the same screen minutes apart; about 3400 for one digit disappearing."""
    return int(cv2.erode((reference ^ text_mask(image)).astype(np.uint8), KERNEL).sum())


def parse_list(text, resolve):
    if text == "unknown":
        return [f for f in range(64) if f not in emerson.KEYS.values()]
    if text == "all":
        return list(range(64))
    return [resolve(x) for x in text.split(",")]


def already_done(log):
    if not log.exists():
        return set()
    with log.open(newline="") as f:
        return {(int(row[1]), int(row[2])) for row in csv.reader(f) if row}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--devices", default="all", help="comma list or 'all' (the normal device first, then likely ones)")
    p.add_argument("--functions", default="all", help="comma list of numbers/key names, 'unknown' or 'all'")
    p.add_argument("--frames", type=int, default=3)
    p.add_argument("--settle", type=float, default=1.5, help="seconds to wait after sending")
    p.add_argument("--threshold", type=int, default=600, help="changed text pixels that count as a reaction")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--log", type=Path, default=LOG_FILE, help="CSV of sent codes; a different file starts a separate scan")
    p.add_argument("--keep-going", action="store_true",
                   help="log reactions and carry on; for scans where reflections of people moving trip it")
    args = p.parse_args()

    if args.devices == "all":
        devices = [emerson.DEFAULT_DEVICE] + remote.device_order(emerson.DEFAULT_DEVICE)
    else:
        devices = parse_list(args.devices, remote.parse_int)
    functions = parse_list(args.functions, remote.resolve_function)
    done = already_done(args.log)
    plan = [(d, f) for d in devices for f in functions if (d, f) not in done and (d, f) not in NEVER_SEND]

    out = HERE / "shots"
    out.mkdir(exist_ok=True)
    tx = remote.Transmitter(remote.find_port())
    cam = Camera(args.camera)
    try:
        first = cam.frame()
        cv2.imwrite(str(out / f"scan_reference_{int(time.time())}.jpg"), first)
        reference = text_mask(first)
        print(f"{len(plan)} codes to send, {len(done)} already logged", flush=True)
        peak = 0
        for n, (device, function) in enumerate(plan, 1):
            reference = text_mask(cam.frame())  # just before sending, so lighting drift doesn't add up
            tx.emerson(device, function, args.frames)
            cam.settle(args.settle)
            after = cam.frame()
            change = text_change(reference, after)
            peak = max(peak, change)
            with args.log.open("a", newline="") as f:
                csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"), device, function, change])
            if n % 50 == 0:
                print(f"[{n}/{len(plan)}] device {device} function {function}: {change} (peak {peak})", flush=True)
            if change >= args.threshold:
                # A real change stays on screen; a camera wobble or passing reflection doesn't.
                cam.settle(4)
                again = cam.frame()
                recheck = text_change(reference, again)
                path = out / f"reaction_d{device}_f{function}_{int(time.time())}.jpg"
                cv2.imwrite(str(path), again)
                if recheck >= args.threshold:
                    print(f"REACTION at device {device} function {function} ({change}, then {recheck}): {path}", flush=True)
                    if not args.keep_going:
                        return
                    continue
                print(f"transient at device {device} function {function} ({change}, then {recheck}): {path}", flush=True)
        print(f"finished with no reaction; peak {peak}", flush=True)
    finally:
        cam.close()


if __name__ == "__main__":
    main()
