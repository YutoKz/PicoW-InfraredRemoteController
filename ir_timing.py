"""Convert microsecond envelopes to the counts used by the TX PIO program."""
from array import array
from presets import validate_preset


def encode(preset):
    validate_preset(preset)
    carrier = preset["carrier_hz"]
    pulses = preset["pulses_us"]
    words = array("I")
    for i in range(0, len(pulses), 2):
        # One carrier cycle: high, low, low/jump.
        words.append(max(1, (pulses[i] * carrier + 500000) // 1000000))
        space = pulses[i + 1] if i + 1 < len(pulses) else 1000
        ticks = (space * carrier * 3 + 500000) // 1000000
        # 2 space setup + (X+1) loop + 4 mark setup = X+7 cycles.
        words.append(max(0, ticks - 7))
    words.append(0)  # Completion sentinel, not an IR mark.
    return words
