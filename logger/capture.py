#!/usr/bin/env python3
"""Run one logging session.

Starts the Nano, splits its output into one CSV per channel, and sends Brrr
notifications that name each cell.

Usage:
    python3 logger/capture.py fridge
    python3 logger/capture.py oven-60C --port /dev/cu.usbserial-1420

Env:
    BRRR_SECRET   your brrr webhook secret (br_usr_...). Unset = no notifications.
                  Set it to "dry-run" to print notifications instead of sending.
"""
import argparse
import glob
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime

import serial

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STALL_SECONDS = 30


def notify(title, message, level="active"):
    secret = os.environ.get("BRRR_SECRET")
    if not secret:
        return
    if secret == "dry-run":
        print(f"[notify:{level}] {title} | {message}")
        return
    body = {
        "title": title,
        "message": message,
        "interruption_level": level,   # passive | active | time-sensitive
        "thread_id": "battery-ia",     # groups these notifications together
    }
    req = urllib.request.Request(
        f"https://api.brrr.now/v1/{secret}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "User-Agent": "battery-ia/1.0"},
    )
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:  # never let a failed notification kill a run
        print(f"(notification failed: {e})")


def load_names(path):
    if path and os.path.exists(path):
        with open(path) as f:
            return {str(k): str(v) for k, v in json.load(f).items()}
    return {}


def channel_label(ch, names):
    return f"{names[ch]} (ch{ch})" if ch in names else f"ch{ch}"


def safe(text):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", text)


def fmt_duration(seconds):
    m = int(seconds // 60)
    return f"{m // 60}h{m % 60:02d}m" if m >= 60 else f"{m}m"


def find_port():
    ports = (glob.glob("/dev/cu.usbserial*") + glob.glob("/dev/cu.usbmodem*")
             + glob.glob("/dev/cu.wchusbserial*"))
    return ports[0] if ports else None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("label", nargs="*", help="what this session is, e.g. fridge or oven-60C")
    ap.add_argument("--port", help="serial port (auto-detected if omitted)")
    ap.add_argument("--config", default=os.path.join(ROOT, "channels.json"),
                    help="channel names (default: channels.json)")
    args = ap.parse_args()

    label = "_".join(args.label) or "run"
    names = load_names(args.config)
    port = args.port or find_port()
    if not port:
        notify("Battery IA", "No Arduino found - check the cable.", "time-sensitive")
        sys.exit("No Arduino found - check the cable.")

    started_at = datetime.now()
    folder = os.path.join(ROOT, "runs", f"{started_at:%Y-%m-%d_%H%M}_{safe(label)}")
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "meta.json"), "w") as f:
        json.dump({"label": label, "started_at": started_at.isoformat(timespec="seconds"),
                   "port": port, "channels": names}, f, indent=2)

    files, stats = {}, {}
    header = None
    started = stalled = False
    last_data = time.time()

    try:
        with serial.Serial(port, 115200, timeout=2) as ser:
            print(f"Saving to {folder}/")
            while True:
                line = ser.readline().decode(errors="ignore").strip()

                if not line:
                    if started and not stalled and time.time() - last_data > STALL_SECONDS:
                        stalled = True
                        notify("Battery IA: stalled",
                               f"{label}: no data for {STALL_SECONDS}s.", "time-sensitive")
                    continue
                last_data, stalled = time.time(), False

                if line.startswith("#"):
                    print(line)
                    if "ready" in line:
                        ser.write(b"g")
                    elif "started" in line:
                        started = True
                        notify("Battery IA", f"{label}: run started.", "passive")
                    elif "reached cutoff" in line:
                        ch = re.search(r"channel (\d+)", line).group(1)
                        s = stats.get(ch)
                        detail = ""
                        if s:
                            avg = f", avg {s['temp_sum'] / s['temp_n']:.1f}°C" if s["temp_n"] else ""
                            detail = f": {s['mAh']:.0f} mAh in {fmt_duration(s['time'])}{avg}"
                        notify(f"{channel_label(ch, names)} finished", f"{label}{detail}", "passive")
                    elif "all done" in line:
                        notify("Battery IA: all done",
                               f"{label}: every channel finished. Unplug the cells.", "active")
                        break
                    elif "ERROR" in line:
                        notify("Battery IA: error", line.lstrip("# "), "time-sensitive")
                        sys.exit(1)
                    continue

                if line.startswith("ch,"):
                    header = line.split(",", 1)[1]
                    continue

                parts = line.split(",")
                if len(parts) != 6 or not parts[0].isdigit() or header is None:
                    continue  # serial noise
                ch, row = parts[0], line.split(",", 1)[1]
                if ch not in files:
                    fname = f"ch{ch}_{safe(names[ch])}.csv" if ch in names else f"ch{ch}.csv"
                    files[ch] = open(os.path.join(folder, fname), "w")
                    files[ch].write(header + "\n")
                files[ch].write(row + "\n")
                files[ch].flush()   # data is on disk even if the cable is pulled

                s = stats.setdefault(ch, {"temp_sum": 0.0, "temp_n": 0, "time": 0.0, "mAh": 0.0})
                try:
                    s["time"], s["mAh"] = float(parts[1]), float(parts[5])
                    if parts[2]:
                        s["temp_sum"] += float(parts[2])
                        s["temp_n"] += 1
                except ValueError:
                    pass

    except serial.SerialException as e:
        notify("Battery IA: disconnected", f"{label}: lost connection to the Nano.", "time-sensitive")
        sys.exit(f"Serial error: {e}")
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        for f in files.values():
            f.close()
    print(f"Done. Data in {folder}/")


if __name__ == "__main__":
    main()
