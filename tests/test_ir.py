"""Host tests: simulate PIO instructions and receiver edges; not electrical tests."""
import ast
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ir_timing import encode
from presets import MAX_PULSES


def source_program():
    """Read the actual TX function, preserving its jumps, wrap and side sets."""
    tree = ast.parse(Path("ir_tx.py").read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_transmit")
    instructions, labels = [], {}
    wrap_start = wrap_end = 0
    for statement in function.body:
        call = statement.value
        side = None
        if isinstance(call.func, ast.Attribute):
            side = call.args[0].value
            call = call.func.value
        op = call.func.id
        args = [a.id if isinstance(a, ast.Name) else a.value for a in call.args]
        if op == "label":
            labels[args[0]] = len(instructions)
        elif op == "wrap_target":
            wrap_start = len(instructions)
        elif op == "wrap":
            wrap_end = len(instructions) - 1
        else:
            instructions.append((op, args, side))
    return instructions, labels, wrap_start, wrap_end


def run_pio(words):
    instructions, labels, wrap_start, wrap_end = source_program()
    registers = {"x": 0, "osr": 0, "isr": 0, "null": 0}
    pc, tick, level = 0, 0, 0
    edges = []
    queue = iter(words)
    for _ in range(1000000):
        op, args, side = instructions[pc]
        if side != level:
            edges.append((tick, side))
            level = side
        next_pc = wrap_start if pc == wrap_end else pc + 1
        if op == "pull":
            registers["osr"] = next(queue)
        elif op == "mov":
            registers[args[0]] = registers[args[1]]
        elif op == "jmp":
            if len(args) == 1:
                next_pc = labels[args[0]]
            elif args[0] == "not_x" and registers["x"] == 0:
                next_pc = labels[args[1]]
            elif args[0] == "x_dec":
                if registers["x"] != 0:
                    next_pc = labels[args[1]]
                registers["x"] = (registers["x"] - 1) & 0xffffffff
        elif op == "push":
            return edges, level
        elif op != "nop":
            raise AssertionError("Unsupported instruction: " + op)
        pc, tick = next_pc, tick + 1
    raise AssertionError("PIO failed to finish")


class PIOTimingTests(unittest.TestCase):
    def test_carrier_envelope_and_completion(self):
        pulses = [9000, 4500, 560, 1690, 560, 40000, 3400, 1750, 430]
        for hz in (30000, 36000, 38000, 40000, 56000, 60000):
            with self.subTest(carrier=hz):
                preset = {"version": 1, "id": "test", "label": "test", "carrier_hz": hz, "pulses_us": pulses}
                edges, final_level = run_pio(encode(preset))
                self.assertEqual(final_level, 0)
                rising = [tick for tick, level in edges if level == 1]
                groups = []
                for tick in rising:
                    if not groups or tick - groups[-1][-1] > 3:
                        groups.append([])
                    groups[-1].append(tick)
                self.assertEqual(len(groups), (len(pulses) + 1) // 2)
                for i, group in enumerate(groups):
                    self.assertLessEqual(abs(len(group) * 1e6 / hz - pulses[2*i]), 0.5e6 / hz + 1e-6)
                    if i + 1 < len(groups):
                        actual_space = (groups[i+1][0] - (group[-1] + 3)) * 1e6 / (3*hz)
                        self.assertLessEqual(abs(actual_space - pulses[2*i+1]), 0.5e6 / (3*hz) + 1e-6)
                # Carrier duty is 1/3; every high-to-low interval is one PIO tick.
                for index in range(0, len(edges), 2):
                    self.assertEqual(edges[index+1][0] - edges[index][0], 1)

    def test_maximum_supported_edge_count(self):
        preset = {"version": 1, "id": "long", "label": "long", "carrier_hz": 38000,
                  "pulses_us": [560] * MAX_PULSES}
        edges, level = run_pio(encode(preset))
        self.assertEqual(level, 0)
        self.assertGreater(len(edges), MAX_PULSES)


class FakePin:
    IN, OUT, PULL_UP, IRQ_RISING, IRQ_FALLING = 0, 1, 2, 4, 8

    def __init__(self, *_args, **_kwargs):
        self.level = 1
        self.handler = None

    def value(self):
        return self.level

    def irq(self, handler=None, **_kwargs):
        self.handler = handler


class ReceiverTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.events = []
        self.clock = SimpleNamespace(ticks_us=lambda: self.now % (1 << 30),
                                     ticks_ms=lambda: self.now // 1000,
                                     ticks_diff=lambda a, b: ((a-b+(1 << 29)) % (1 << 30)) - (1 << 29),
                                     sleep_ms=self.sleep)
        fake_machine = SimpleNamespace(Pin=FakePin, disable_irq=lambda: 0, enable_irq=lambda _: None)
        spec = importlib.util.spec_from_file_location("read_test_module", "read.py")
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {"machine": fake_machine,
                                      "micropython": SimpleNamespace(alloc_emergency_exception_buf=lambda _: None),
                                      "time": self.clock}):
            spec.loader.exec_module(self.module)
        self.receiver = self.module.IRReceiver(timeout_ms=1000)

    def sleep(self, milliseconds):
        target = self.now + milliseconds * 1000
        while self.events and self.events[0][0] <= target:
            self.now, level = self.events.pop(0)
            self.receiver.pin.level = level
            if self.receiver.pin.handler:
                self.receiver.pin.handler(self.receiver.pin)
        self.now = target

    def schedule(self, pulses):
        at = self.now + 10000
        level = 0
        self.events = [(at, level)]
        for duration in pulses:
            at += duration
            level = 1 - level
            self.events.append((at, level))

    def test_complete_multiframe_capture_excludes_idle(self):
        pulses = [3500, 1750] + [430, 430] * 150 + [430, 40000, 3500, 1750, 430]
        self.schedule(pulses)
        self.assertEqual(self.receiver.capture(), pulses)
        self.assertIsNone(self.receiver.pin.handler)

    def test_ticks_wrap(self):
        self.now = (1 << 30) - 12000
        pulses = [9000, 4500, 560]
        self.schedule(pulses)
        self.assertEqual(self.receiver.capture(), pulses)

    def test_final_idle_not_counted_against_signal_limit(self):
        self.receiver.timeout_ms = 5000
        pulses = [500000, 100000, 500000, 100000, 500000, 100000, 199500]
        self.schedule(pulses)
        self.assertEqual(self.receiver.capture(), pulses)

    def test_idle_timeout_detaches_irq(self):
        with self.assertRaises(ValueError):
            self.receiver.capture()
        self.assertIsNone(self.receiver.pin.handler)

    def test_stuck_low_rejected(self):
        self.receiver.pin.level = 0
        with self.assertRaises(ValueError):
            self.receiver.capture()

    def test_overflow_never_returns_partial_signal(self):
        self.schedule([100] * (MAX_PULSES + 2))
        with self.assertRaises(ValueError):
            self.receiver.capture()
        self.assertIsNone(self.receiver.pin.handler)


if __name__ == "__main__":
    unittest.main()
