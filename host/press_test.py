"""Try keys on device 41 as single presses and long holds, watching the webcam.

  python press_test.py                  8 and 9, then CH up/down with shorter holds
  python press_test.py --label menu     tag saved frames, e.g. after a front-panel MENU press
  python press_test.py --power-on       send F63 every second until the TV is switched on,
                                        then run the presses (the manual's order: main power, then SLEEP)

Stops at the first reaction, so a live CH key can't keep changing a value.
"""

import argparse
import time

import cv2

import emerson
import remote
from scan import HERE, text_change, text_mask
from watch import Camera

# (key, frames). One frame is a tap, 50 is about 5 s held. CH holds stay short because CH changes values.
PRESSES = [("8", 1), ("8", 50), ("9", 1), ("9", 50), ("ch+", 1), ("ch-", 1), ("ch+", 10), ("ch-", 10)]
OUT = HERE / "shots"


def wait_for_power_on(tx, cam, threshold, minutes=5):
    """Send the service code every second; the TV gets it as soon as it comes on."""
    off = text_mask(cam.frame())
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        tx.emerson(emerson.DEFAULT_DEVICE, 63, 3)
        change = text_change(off, cam.frame())
        if change >= threshold:
            print(f"TV came on ({change}); sent F63 within about a second", flush=True)
            for _ in range(2):
                cam.settle(1)
                tx.emerson(emerson.DEFAULT_DEVICE, 63, 3)
            cam.settle(3)
            return True
        cam.settle(0.5)
    print("TV never came on", flush=True)
    return False


def run_presses(tx, cam, label, threshold):
    first = cam.frame()
    stamp = int(time.time())
    cv2.imwrite(str(OUT / f"press_{label}_{stamp}_start.jpg"), first)
    print(OUT / f"press_{label}_{stamp}_start.jpg", flush=True)
    reference = text_mask(first)
    for key, frames in PRESSES:
        tx.emerson(emerson.DEFAULT_DEVICE, emerson.KEYS[key], frames)
        cam.settle(1.5)
        after = cam.frame()
        change = text_change(reference, after)
        print(f"{key} x{frames}: {change}", flush=True)
        if change >= threshold:
            path = OUT / f"press_{label}_{stamp}_{key}x{frames}.jpg"
            cv2.imwrite(str(path), after)
            print(f"REACTION: {path}", flush=True)
            return True
        cam.settle(2)
    path = OUT / f"press_{label}_{stamp}_end.jpg"
    cv2.imwrite(str(path), cam.frame())
    print(f"no reaction: {path}", flush=True)
    return False


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--label", default="version")
    p.add_argument("--power-on", action="store_true")
    p.add_argument("--threshold", type=int, default=600)
    p.add_argument("--camera", type=int, default=0)
    args = p.parse_args()

    tx = remote.Transmitter(remote.find_port())
    cam = Camera(args.camera)
    try:
        if args.power_on and not wait_for_power_on(tx, cam, args.threshold):
            return
        run_presses(tx, cam, "poweron" if args.power_on else args.label, args.threshold)
    finally:
        cam.close()


if __name__ == "__main__":
    main()
