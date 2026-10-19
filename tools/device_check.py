"""Run via mpremote on the Pico W. Does not connect Wi-Fi or emit IR."""
import gc
import sys
import config
from settings import validate
from presets import PresetStore
from ir_tx import IRTransmitter, _transmit
from http_server import Application
import wifi
import send

validate(config)
if config.IR_RECEIVE_PIN is not None:
    from read import IRReceiver
    receiver = IRReceiver(config.IR_RECEIVE_PIN, config.CAPTURE_IDLE_MS, config.CAPTURE_TIMEOUT_MS)
    print("Receiver idle level (expect 1):", receiver.pin.value())
store = PresetStore(config.PRESET_DIRECTORY)
for preset_id in store.ids():
    store.load(preset_id)
with open("index.html", "r") as page:
    assert page.read(15).lower().startswith("<!doctype html>")
gc.collect()
print("MicroPython:", sys.version)
print("Imports/config/PIO assembly: OK; presets:", len(store.ids()))
print("Free heap bytes:", gc.mem_free())
print("No IR was sent. Wi-Fi and appliance operation still require a live test.")
