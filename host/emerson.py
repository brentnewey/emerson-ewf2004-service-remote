"""Emerson/Funai CRT IR protocol (JP1 "Emerson"): encode, decode and known codes.

IRP: {36.7k,872}<1,-1|1,-3>(4,-4,D:6,F:6,~D:6,~F:6,1,-39)+

Device/function numbers use JP1 convention (fields sent LSB-first), so they can
be compared directly with hifi-remote.com / IrScrutinizer / RemoteMaster.
"""

FREQ_HZ = 36700
UNIT_US = 872

# Normal device code, decoded from the Symphonic ST424FF (Funai CRT) capture in
# Flipper-IRDB. Unconfirmed on the EWF2004 until Phase 1 passes.
DEFAULT_DEVICE = 41

KEYS = {
    "power": 32,
    "vol+": 48,
    "vol-": 49,
    "ch+": 16,
    "ch-": 8,
    "mute": 51,
    "menu": 47,
    "sleep": 11,  # not in the Flipper capture; from probonopd/irdb Symphonic/TV/41,-1.csv
    "select": 46,
    "input": 13,
    "display": 15,
    "set+": 6,
    "set-": 7,
    "1": 31, "2": 33, "3": 34, "4": 35, "5": 36,
    "6": 37, "7": 38, "8": 39, "9": 40, "0": 41,
}


def frame_bits(device, function, factory=False):
    """The 24 bits in transmit order.

    factory=True is the service remote's format (J1 linked, "JW5.0 FACTORY" on the
    board): the second 12 bits repeat device and function instead of complementing them.
    """
    if not (0 <= device < 64 and 0 <= function < 64):
        raise ValueError("device and function must be 0-63")
    check = device | function << 6 if factory else (~device & 63) | (~function & 63) << 6
    data = device | function << 6 | check << 12
    return [(data >> i) & 1 for i in range(24)]


def encode(device, function, factory=False):
    """Mark/space durations in microseconds for one frame, including trailing gap."""
    t = [4 * UNIT_US, 4 * UNIT_US]
    for bit in frame_bits(device, function, factory):
        t += [UNIT_US, 3 * UNIT_US if bit else UNIT_US]
    t += [UNIT_US, 39 * UNIT_US]
    return t


def decode(timings, tolerance=0.3, factory=False):
    """Return (device, function) for a raw capture, or None if it isn't an Emerson frame
    (of the factory/service format when factory=True).

    Accepts captures with or without the trailing gap.
    """
    def near(value, units):
        return abs(value - units * UNIT_US) <= units * UNIT_US * tolerance

    if len(timings) < 50 or not (near(timings[0], 4) and near(timings[1], 4)):
        return None
    bits = []
    for mark, space in zip(timings[2:50:2], timings[3:50:2]):
        if not near(mark, 1):
            return None
        if near(space, 1):
            bits.append(0)
        elif near(space, 3):
            bits.append(1)
        else:
            return None
    data = sum(b << i for i, b in enumerate(bits))
    device, function = data & 63, (data >> 6) & 63
    if (data >> 12) != (data & 0xFFF if factory else ~data & 0xFFF):
        return None
    return device, function
