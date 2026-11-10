"""Send IR codes and use the webcam to see whether the TV's screen changed.

  python watch.py 41 49                 send one code, save before/after frames
  python watch.py 41 49 --frames 3 --settle 2.5 --camera 0 --out shots

Prints the fraction of pixels that changed, so a scan can flag a reaction without
someone watching. Reflections in the glass move too, so look at the saved frames
before trusting a small number.
"""

import argparse
import time
from pathlib import Path

import cv2

import emerson
import remote

DIFF_THRESHOLD = 40  # per-pixel grey level change that counts as changed


class Camera:
    def __init__(self, index=0, warmup=4):
        self.cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise SystemExit(f"Can't open camera {index}. Close any other app using it.")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        self.settle(warmup)  # the camera unfolds and adjusts exposure when opened
        # Lock focus and exposure once settled, so refocusing can't look like a screen change.
        self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 0.25)
        self.settle(1)

    def settle(self, seconds):
        """Keep reading while waiting, so the next frame isn't a stale buffered one."""
        end = time.time() + seconds
        while time.time() < end:
            self.cap.read()

    def frame(self):
        for _ in range(5):
            self.cap.read()
        ok, image = self.cap.read()
        if not ok:
            raise RuntimeError("camera returned no frame")
        return image

    def close(self):
        self.cap.release()


def changed_fraction(before, after):
    diff = cv2.absdiff(cv2.cvtColor(before, cv2.COLOR_BGR2GRAY), cv2.cvtColor(after, cv2.COLOR_BGR2GRAY))
    return float((diff > DIFF_THRESHOLD).mean())


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("device", type=remote.parse_int)
    p.add_argument("function", type=remote.resolve_function, help="0-63 or a key name")
    p.add_argument("--frames", type=int, default=3)
    p.add_argument("--settle", type=float, default=2.5, help="seconds to wait before the after frame")
    p.add_argument("--camera", type=int, default=0)
    p.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "shots")
    args = p.parse_args()

    args.out.mkdir(exist_ok=True)
    tx = remote.Transmitter(remote.find_port())
    cam = Camera(args.camera)
    try:
        before = cam.frame()
        print(tx.emerson(args.device, args.function, args.frames))
        cam.settle(args.settle)
        after = cam.frame()
    finally:
        cam.close()
    stem = f"d{args.device}_f{args.function}_{int(time.time())}"
    cv2.imwrite(str(args.out / f"{stem}_before.jpg"), before)
    cv2.imwrite(str(args.out / f"{stem}_after.jpg"), after)
    print(f"changed {changed_fraction(before, after) * 100:.2f}% of pixels")
    print(args.out / f"{stem}_after.jpg")


if __name__ == "__main__":
    main()
