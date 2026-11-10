"""Check the encoder against a real Funai CRT capture (Symphonic ST424FF, Flipper-IRDB)."""

from pathlib import Path

import emerson

REFERENCE = Path(__file__).resolve().parent.parent / "reference" / "Symphonic_ST424FF.ir"

# IRDB button name -> our key name
NAMES = {
    "Power": "power", "Vol_up": "vol+", "Vol_dn": "vol-", "Ch_next": "ch+",
    "Ch_prev": "ch-", "Mute": "mute", "Menu": "menu", "Select": "select",
    "Input": "input", "Display": "display", "Set +": "set+", "Set -": "set-",
    **{str(n): str(n) for n in range(10)},
}


def load_reference():
    signals, name = {}, None
    for line in REFERENCE.read_text().splitlines():
        if line.startswith("name:"):
            name = line[5:].strip()
        elif line.startswith("data:"):
            signals[name] = [int(x) for x in line[5:].split()]
    return signals


def test_encode_matches_capture():
    signals = load_reference()
    assert set(NAMES) <= set(signals)
    for irdb_name, key in NAMES.items():
        assert emerson.encode(emerson.DEFAULT_DEVICE, emerson.KEYS[key]) == signals[irdb_name], irdb_name


def test_decode_round_trip():
    for device in range(64):
        for function in range(64):
            assert emerson.decode(emerson.encode(device, function)) == (device, function)


def test_decode_rejects_bad_complement():
    t = emerson.encode(41, 32)
    t[3] = 3 * emerson.UNIT_US if t[3] == emerson.UNIT_US else emerson.UNIT_US
    assert emerson.decode(t) is None


# Key 8 on a real factory remote (J1 linked), captured by the Uno's TSOP38238.
FACTORY_8 = [int(x) for x in """3450 3450 900 2550 900 850 850 900 850 2550 900 900 850 2550 900 2550 900 2550
900 2550 900 850 850 900 850 2550 900 2600 850 900 850 850 850 2600 850 900 850 2550 900 2550 900 2600 850 2600
850 900 850 850 850 2600 850""".split()]


def test_factory_capture():
    assert emerson.decode(FACTORY_8) is None
    assert emerson.decode(FACTORY_8, factory=True) == (41, 39)
    assert all(abs(a - b) < 300 for a, b in zip(emerson.encode(41, 39, factory=True), FACTORY_8))


def test_factory_round_trip():
    for device in range(64):
        for function in range(64):
            t = emerson.encode(device, function, factory=True)
            assert emerson.decode(t, factory=True) == (device, function)
            assert emerson.decode(t) is None  # a value can't equal its own complement


if __name__ == "__main__":
    test_encode_matches_capture()
    test_decode_round_trip()
    test_decode_rejects_bad_complement()
    test_factory_capture()
    test_factory_round_trip()
    print("all tests passed")
