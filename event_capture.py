import argparse
import csv
import os
import sys
import time
from datetime import datetime

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed. Run: pip install pyserial")

DATA_DIR = "data"
MANIFEST = os.path.join(DATA_DIR, "manifest.csv")


def ensure_manifest():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(MANIFEST):
        with open(MANIFEST, "w", newline="") as f:
            csv.writer(f).writerow(
                ["event_id", "label", "timestamp",
                 "onset_file", "steady_file", "offset_file",
                 "steady_rows"]
            )


def next_label(prev):
    prompt = "\nDevice label"
    if prev:
        prompt += f" [{prev}]"
    prompt += ": "
    try:
        s = input(prompt).strip()
    except EOFError:
        return prev
    return s if s else prev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="serial port of the ESP32")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    ensure_manifest()
    ser = serial.Serial(args.port, args.baud, timeout=2)
    time.sleep(2)  # let the board reset after opening the port
    ser.reset_input_buffer()

    print("Listening. Waiting for the board to say READY...")
    print("(Ctrl-C to stop.)")

    label = ""
    # Per-event accumulation
    onset, offset, steady = [], [], []
    section = None          # None | "pre" | "onset" | "steady" | "offset"
    event_id = None
    armed_prompt = True

    def flush_event():
        nonlocal onset, offset, steady, event_id
        if event_id is None:
            return
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"{label or 'unlabelled'}_{event_id}"
        onset_f  = f"{base}_onset.csv"
        steady_f = f"{base}_steady.csv"
        offset_f = f"{base}_offset.csv"

        with open(os.path.join(DATA_DIR, onset_f), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["sample"])
            w.writerows([[v] for v in onset])
        with open(os.path.join(DATA_DIR, offset_f), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["sample"])
            w.writerows([[v] for v in offset])
        with open(os.path.join(DATA_DIR, steady_f), "w", newline="") as f:
            w = csv.writer(f); w.writerow(["rms_counts", "amps", "crest"])
            w.writerows(steady)

        with open(MANIFEST, "a", newline="") as f:
            csv.writer(f).writerow(
                [event_id, label, ts, onset_f, steady_f, offset_f, len(steady)]
            )

        print(f"  saved event {event_id} '{label}': "
              f"{len(onset)} onset, {len(steady)} steady rows, "
              f"{len(offset)} offset")
        onset, offset, steady = [], [], []
        event_id = None

    try:
        while True:
            raw = ser.readline().decode(errors="replace").strip()
            if not raw:
                continue

            if raw == "READY":
                if armed_prompt:
                    label = next_label(label)
                    armed_prompt = False
                continue

            if raw.startswith("EVENT_START"):
                event_id = raw.split()[1]
                armed_prompt = True   # prompt again after this event ends
                print(f"Event {event_id} '{label}' - capturing...")
                continue

            if raw == "PRE_TRIGGER":
                section = "pre"; continue
            if raw.startswith("TRANSIENT"):
                section = "onset" if "ONSET" in raw else "offset"; continue
            if raw == "STEADY_BEGIN":
                section = "steady"; continue
            if raw == "STEADY_END":
                section = None; continue

            if raw.startswith("STEADY "):
                parts = raw[len("STEADY "):].split(",")
                if len(parts) == 3:
                    steady.append(parts)
                continue

            if raw.startswith("EVENT_END"):
                flush_event()
                section = None
                continue

            # Otherwise it's a numeric sample line belonging to a section.
            try:
                val = int(raw)
            except ValueError:
                continue
            if section in ("pre", "onset"):
                onset.append(val)     # pre-trigger prepends onto onset
            elif section == "offset":
                offset.append(val)

    except KeyboardInterrupt:
        print("\nStopping.")
        flush_event()
        ser.close()


if __name__ == "__main__":
    main()