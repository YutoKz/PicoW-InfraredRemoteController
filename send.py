"""USB REPL: import send; send.send('cool_26'). No transmission on import."""
from presets import PresetStore


def send(preset_id):
    import config
    from ir_tx import IRTransmitter
    preset = PresetStore(config.PRESET_DIRECTORY).load(preset_id)
    IRTransmitter(config.IR_SEND_PIN, config.IR_STATE_MACHINE).send(preset)
    print("IR sent:", preset_id, "(appliance state is not confirmed)")
