"""Portable validation and storage of complete IR command envelopes."""
import json
import os

MAX_PULSES = 2047
MAX_SIGNAL_US = 2000000
MAX_PRESETS = 32
MAX_FILE_BYTES = 20000


def validate_id(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 40:
        raise ValueError("ID must be 1-40 characters")
    if any(c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in value):
        raise ValueError("ID: use lowercase a-z, 0-9, _ or -")
    return value


def validate_label(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 60:
        raise ValueError("Label must be 1-60 characters")
    if any(ord(c) < 32 for c in value):
        raise ValueError("Label contains a control character")
    return value


def validate_carrier(value):
    if type(value) is not int or not 30000 <= value <= 60000:
        raise ValueError("Carrier must be 30000-60000 Hz")
    return value


def validate_preset(preset):
    if not isinstance(preset, dict) or type(preset.get("version")) is not int or preset.get("version") != 1:
        raise ValueError("Unsupported preset format")
    validate_id(preset.get("id"))
    validate_label(preset.get("label"))
    validate_carrier(preset.get("carrier_hz"))
    pulses = preset.get("pulses_us")
    if not isinstance(pulses, list) or not 3 <= len(pulses) <= MAX_PULSES:
        raise ValueError("Invalid pulse count")
    if len(pulses) % 2 != 1:
        raise ValueError("Signal must begin and end with a mark (odd pulse count)")
    for duration in pulses:
        if type(duration) is not int or not 100 <= duration <= 500000:
            raise ValueError("Each pulse must be 100-500000 microseconds")
    if sum(pulses) > MAX_SIGNAL_US:
        raise ValueError("Signal exceeds two seconds")
    return preset


class PresetStore:
    def __init__(self, directory="codes"):
        self.directory = directory.rstrip("/")
        try:
            os.mkdir(self.directory)
        except OSError:
            os.listdir(self.directory)

    def _path(self, preset_id):
        return self.directory + "/" + validate_id(preset_id) + ".json"

    def ids(self):
        result = []
        for name in os.listdir(self.directory):
            if name.endswith(".json"):
                result.append(validate_id(name[:-5]))
        if len(result) > MAX_PRESETS:
            raise ValueError("Too many preset files (maximum 32)")
        return sorted(result)

    def load(self, preset_id):
        path = self._path(preset_id)
        if preset_id not in self.ids():
            raise KeyError(preset_id)
        if os.stat(path)[6] > MAX_FILE_BYTES:
            raise ValueError("Preset file is too large")
        with open(path, "r") as file:
            result = validate_preset(json.load(file))
        if result["id"] != preset_id:
            raise ValueError("Preset ID does not match filename")
        return result

    def summaries(self):
        result = []
        for preset_id in self.ids():
            preset = self.load(preset_id)
            result.append({"id": preset_id, "label": preset["label"],
                           "carrier_hz": preset["carrier_hz"], "pulse_count": len(preset["pulses_us"])})
        return result

    def save(self, preset):
        validate_preset(preset)
        existing = self.ids()
        if preset["id"] not in existing and len(existing) >= MAX_PRESETS:
            raise ValueError("Maximum 32 presets; remove an unused preset first")
        path = self._path(preset["id"])
        temporary = path + ".tmp"
        try:
            with open(temporary, "w") as file:
                json.dump(preset, file)
            if os.stat(temporary)[6] > MAX_FILE_BYTES:
                raise ValueError("Preset file is too large")
            # Atomic replacement on the Pico W firmware's littlefs filesystem.
            # Do not delete the old file before rename.
            os.rename(temporary, path)
        finally:
            try:
                os.remove(temporary)
            except OSError:
                pass

    def delete(self, preset_id):
        if preset_id not in self.ids():
            raise KeyError(preset_id)
        os.remove(self._path(preset_id))
