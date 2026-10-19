"""Learn active-low demodulated IR without printing or allocating in the IRQ."""
from array import array
import gc
import time
import micropython
from machine import Pin, disable_irq, enable_irq
from presets import (MAX_PULSES, MAX_SIGNAL_US, PresetStore, validate_preset,
                     validate_id, validate_label, validate_carrier)

micropython.alloc_emergency_exception_buf(100)


class IRReceiver:
    def __init__(self, pin=26, idle_ms=120, timeout_ms=10000):
        self.pin = Pin(pin, Pin.IN, Pin.PULL_UP)
        self.idle_us = idle_ms * 1000
        self.timeout_ms = timeout_ms
        self._buffer = array("I", [0] * MAX_PULSES)
        self._started = False
        self._done = False
        self._overflow = False
        self._count = 0
        self._last = 0
        self._first = 0
        self._level = 1

    def _edge(self, pin):
        # Hard IRQ: only small integers and preallocated storage.
        if self._done or self._overflow:
            return
        now = time.ticks_us()
        level = pin.value()
        if not self._started:
            if level == 0:
                self._first = now
                self._last = now
                self._level = 0
                self._started = True
            return
        duration = time.ticks_diff(now, self._last)
        if self._level == 1 and duration >= self.idle_us:
            self._done = True
            return
        if level == self._level or self._count >= MAX_PULSES:
            self._overflow = True
            return
        self._buffer[self._count] = duration
        self._count += 1
        self._last = now
        self._level = level

    def capture(self):
        self._started = self._done = self._overflow = False
        self._count = 0
        self._level = 1
        if self.pin.value() != 1:
            raise ValueError("Receiver must be idle HIGH before learning")
        gc.collect()
        start = time.ticks_ms()
        self.pin.irq(handler=self._edge, trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, hard=True)
        try:
            while True:
                irq_state = disable_irq()
                started, last, first = self._started, self._last, self._first
                level, done, overflow = self._level, self._done, self._overflow
                enable_irq(irq_state)
                if overflow:
                    raise ValueError("Too many edges or missed edge; capture rejected")
                now = time.ticks_us()
                if done or (started and level == 1 and time.ticks_diff(now, last) >= self.idle_us):
                    break
                # The final idle delimiter is not part of the signal duration.
                if started and time.ticks_diff(now, first) > MAX_SIGNAL_US + self.idle_us:
                    raise ValueError("Capture exceeds two seconds; release the button")
                if time.ticks_diff(time.ticks_ms(), start) > self.timeout_ms:
                    raise ValueError("No complete IR signal received before timeout")
                time.sleep_ms(1)
        finally:
            self.pin.irq(handler=None)
        if self._overflow:
            raise ValueError("Capture overflow; no preset saved")
        return list(self._buffer[:self._count])


def learn(preset_id, label, carrier_hz=None, overwrite=False):
    """USB REPL: import read; read.learn('cool_26', '冷房26℃')"""
    import config
    validate_id(preset_id)
    validate_label(label)
    carrier_hz = validate_carrier(config.IR_CARRIER_HZ if carrier_hz is None else carrier_hz)
    if config.IR_RECEIVE_PIN is None:
        raise ValueError("Configure IR_RECEIVE_PIN first")
    store = PresetStore(config.PRESET_DIRECTORY)
    if preset_id in store.ids() and not overwrite:
        raise ValueError("ID already exists; use overwrite=True deliberately")
    receiver = IRReceiver(config.IR_RECEIVE_PIN, config.CAPTURE_IDLE_MS, config.CAPTURE_TIMEOUT_MS)
    print("Ready: point the original remote at the receiver and press once.")
    preset = validate_preset({"version": 1, "id": preset_id, "label": label,
                              "carrier_hz": carrier_hz, "pulses_us": receiver.capture()})
    store.save(preset)
    print("Saved", preset_id, "with", len(preset["pulses_us"]), "pulses")
    return {"id": preset_id, "pulse_count": len(preset["pulses_us"])}
