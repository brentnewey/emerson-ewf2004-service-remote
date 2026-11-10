"""Two short service-mode tests, watched by the webcam. Start with the service screen up.

  python seq_test.py pairs    F63 then each device-41 function back to back (POWER skipped)
  python seq_test.py nec      NEC address 0x0808, all 256 commands (TV/0180 lead)

Stops at the first change that is still there 4 s later.
"""

import argparse
import time

import cv2

import emerson
import remote
from scan import HERE, text_change, text_mask
from watch import Camera


def steps(kind):
    d = emerson.DEFAULT_DEVICE
    if kind == "pairs":
        for f in range(64):
            if f != emerson.KEYS["power"]:
                yield f"F63+F{f}", [f"E {d} 63 3", f"E {d} {f} 3"]
    else:
        for c in range(256):
            yield f"NEC 0x0808 {c:#04x}", [f"N {0x0808} {c} 1"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("kind", choices=["pairs", "nec"])
    p.add_argument("--threshold", type=int, default=600)
    p.add_argument("--start", type=int, default=0, help="step to resume from (NEC: the command number)")
    args = p.parse_args()

    out = HERE / "shots"
    tx = remote.Transmitter(remote.find_port())
    cam = Camera(0)
    try:
        peak = 0
        for name, commands in list(steps(args.kind))[args.start:]:
            reference = text_mask(cam.frame())  # just before sending, so lighting drift doesn't add up
            for c in commands:
                tx.command(c)
            cam.settle(1.5)
            change = text_change(reference, cam.frame())
            peak = max(peak, change)
            if change >= args.threshold:
                cam.settle(4)
                again = cam.frame()
                recheck = text_change(reference, again)
                path = out / f"seq_{args.kind}_{int(time.time())}.jpg"
                cv2.imwrite(str(path), again)
                if recheck >= args.threshold:
                    print(f"REACTION at {name} ({change}, then {recheck}): {path}", flush=True)
                    return
                print(f"transient at {name} ({change}, then {recheck})", flush=True)
        print(f"{args.kind}: no reaction, peak {peak}", flush=True)
    finally:
        cam.close()


if __name__ == "__main__":
    main()
