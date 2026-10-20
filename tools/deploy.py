"""Upload only runtime files. Requires `python -m pip install mpremote`."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FILES = ["config.py", "settings.py", "presets.py", "ir_timing.py", "ir_tx.py",
         "read.py", "send.py", "wifi.py", "http_server.py", "index.html", "main.py"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="auto", help="COM5, /dev/ttyACM0, or auto")
    parser.add_argument("--reset", action="store_true", help="Reboot and start server after upload/check")
    args = parser.parse_args()
    missing = [name for name in FILES if not (ROOT / name).is_file()]
    if missing:
        parser.error("Missing: " + ", ".join(missing) + ". Copy config.example.py to config.py first.")
    base = [sys.executable, "-m", "mpremote", "connect", args.port]
    subprocess.run(base + ["fs", "cp"] + FILES + [":"], cwd=ROOT, check=True)
    subprocess.run(base + ["run", "tools/device_check.py"], cwd=ROOT, check=True)
    if args.reset:
        subprocess.run(base + ["reset"], cwd=ROOT, check=True)
    else:
        print("Uploaded. Reconnect power or run mpremote reset to start the server.")


if __name__ == "__main__":
    main()
