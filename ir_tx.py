"""Pico W hardware-timed IR output; no Python-loop timing calibration."""
import gc
import time
from machine import Pin
import rp2
from ir_timing import encode


@rp2.asm_pio(sideset_init=rp2.PIO.OUT_LOW)
def _transmit():
    wrap_target()
    pull(block).side(0)
    mov(x, osr).side(0)
    jmp(not_x, "done").side(0)
    jmp(x_dec, "mark").side(0)
    label("mark")
    nop().side(1)
    nop().side(0)
    jmp(x_dec, "mark").side(0)
    pull(block).side(0)
    mov(x, osr).side(0)
    label("space")
    jmp(x_dec, "space").side(0)
    wrap()
    label("done")
    mov(isr, null).side(0)
    push(block).side(0)
    label("halt")
    jmp("halt").side(0)


class IRTransmitter:
    def __init__(self, pin=17, state_machine=0):
        self.pin = Pin(pin, Pin.OUT, value=0)
        self.state_machine = state_machine

    def send(self, preset):
        words = encode(preset)
        gc.collect()
        sm = rp2.StateMachine(self.state_machine, _transmit,
                              freq=preset["carrier_hz"] * 3, sideset_base=self.pin)
        try:
            sm.active(1)
            # Native C loop feeds the FIFO while PIO generates the carrier.
            sm.put(words)
            start = time.ticks_ms()
            while not sm.rx_fifo():
                if time.ticks_diff(time.ticks_ms(), start) > 3000:
                    raise OSError("IR transmitter completion timed out")
                time.sleep_ms(1)
            sm.get()  # Wait for actual completion, not merely an empty TX FIFO.
        finally:
            sm.active(0)
            sm.exec("nop().side(0)")
            self.pin.init(Pin.OUT, value=0)
