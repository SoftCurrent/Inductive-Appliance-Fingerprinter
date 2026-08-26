#!/usr/bin/env python3
"""
Inductive Appliance Fingerprinter - live prediction.

Listens to the ESP32, and each time an appliance turns on it extracts the
same features used in training and predicts what the device is. Saves
nothing to disk. The other scripts (capture, extract, classifier) are
untouched.

The feature functions below are copied VERBATIM from extract_features.py.
They must stay identical, or the live features won't match what the model
learned. steady_features is reworked to take the in-memory rows instead of
a file path, but computes the same three numbers.

Usage:
    python predict_live.py --port /dev/cu.usbmodemXXXX
Requires: pyserial, numpy, scikit-learn, joblib
"""

import argparse
import sys
import numpy as np
import joblib

try:
    import serial
except ImportError:
    sys.exit("pyserial not installed. Run: pip install pyserial")

rf = joblib.load("model.joblib")

# The column order the model was trained on. The live feature row MUST be
# in exactly this order.
FEATURE_ORDER = [
    "onset_crest", "inrush_ratio", "settle_frac",
    "h2", "h3", "h4", "h5", "h6", "h7", "thd",
    "steady_rms", "steady_cov", "steady_dur",
]

# ---- feature functions (verbatim from extract_features.py) ------------

def estimate_period(sig, fs_guess=10000, f_line=50):
    if len(sig) < 200:
        return None
    sig = sig - sig.mean()
    nominal = fs_guess / f_line
    lo, hi = int(nominal * 0.4), int(nominal * 2.5)
    hi = min(hi, len(sig) // 2)
    if hi <= lo:
        return None
    corr = np.correlate(sig, sig, mode="full")[len(sig) - 1:]
    window = corr[lo:hi]
    if len(window) == 0:
        return None
    peak = np.argmax(window) + lo
    return peak if peak > 0 else None


def rms(x):
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def harmonic_ratios(sig, period, n_harm=7):
    if period is None or len(sig) < period * 4:
        return [0.0] * (n_harm - 1) + [0.0]
    n_cycles = len(sig) // period
    usable = sig[: n_cycles * period]
    spec = np.abs(np.fft.rfft(usable - usable.mean()))
    fund_bin = n_cycles
    if fund_bin >= len(spec) or spec[fund_bin] < 1e-9:
        return [0.0] * (n_harm - 1) + [0.0]
    fund = spec[fund_bin]
    ratios = []
    harm_power = 0.0
    for h in range(2, n_harm + 1):
        b = fund_bin * h
        val = spec[b] if b < len(spec) else 0.0
        ratios.append(float(val / fund))
        harm_power += val * val
    thd = float(np.sqrt(harm_power) / fund)
    return ratios + [thd]


def envelope_features(sig, period):
    if period is None or len(sig) < period * 3:
        return 0.0, 0.0
    n_cycles = len(sig) // period
    env = np.array([rms(sig[i * period:(i + 1) * period])
                    for i in range(n_cycles)])
    if len(env) < 3 or env[-1] < 1e-9:
        return 0.0, 0.0
    steady = np.median(env[-max(3, len(env) // 4):])
    if steady < 1e-9:
        return 0.0, 0.0
    inrush_ratio = float(env.max() / steady)
    settle = len(env)
    for i in range(len(env)):
        if abs(env[i] - steady) / steady < 0.20:
            settle = i
            break
    settle_frac = float(settle / len(env))
    return inrush_ratio, settle_frac


def steady_features_from_rows(rows):
    """Same three numbers as extract_features.steady_features, but from the
    in-memory steady rows (each is [rms_counts, amps, crest] as strings)."""
    if not rows:
        return 0.0, 0.0, 0
    rms_vals = []
    for r in rows:
        try:
            rms_vals.append(float(r[0]))
        except (ValueError, IndexError):
            pass
    if not rms_vals:
        return 0.0, 0.0, 0
    arr = np.array(rms_vals)
    mean = float(arr.mean())
    cov = float(arr.std() / mean) if mean > 1e-9 else 0.0
    return mean, cov, len(arr)


def build_feature_row(onset_list, steady_rows):
    """Turn one event's raw data into the 13-value row, in FEATURE_ORDER."""
    onset = np.array(onset_list, dtype=float)
    if len(onset) < 400:
        return None  # too short to be a real event

    period = estimate_period(onset)
    crest = (np.abs(onset).max() / rms(onset)) if rms(onset) > 0 else 0.0
    inrush, settle = envelope_features(onset, period)
    harm = harmonic_ratios(onset, period)          # [h2..h7, thd] -> 7 values
    s_mean, s_cov, s_dur = steady_features_from_rows(steady_rows)

    return [
        crest,          # onset_crest
        inrush,         # inrush_ratio
        settle,         # settle_frac
        harm[0],        # h2
        harm[1],        # h3
        harm[2],        # h4
        harm[3],        # h5
        harm[4],        # h6
        harm[5],        # h7
        harm[6],        # thd
        s_mean,         # steady_rms
        s_cov,          # steady_cov
        s_dur,          # steady_dur
    ]


# ---- main -------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", required=True, help="serial port of the ESP32")
    ap.add_argument("--baud", type=int, default=115200)
    args = ap.parse_args()

    ser = serial.Serial(args.port, args.baud, timeout=2)
    print(f"Live prediction ready. Model knows: {sorted(rf.classes_)}")
    print("Turn a device on and I'll guess what it is. (Ctrl-C to stop.)\n")

    onset, steady = [], []
    section = None

    def predict_event():
        nonlocal onset, steady
        row = build_feature_row(onset, steady)
        if row is not None:
            proba = rf.predict_proba([row])[0]
            i = int(np.argmax(proba))
            guess = rf.classes_[i]
            conf = float(proba[i])
            print(f"  --> Detected: {guess}   ({conf:.0%} confident)")
        else:
            print("  --> event too short to classify")
        onset, steady = [], []

    try:
        while True:
            raw = ser.readline().decode(errors="replace").strip()
            if not raw:
                continue

            if raw == "READY":
                continue
            if raw.startswith("EVENT_START"):
                print("Event detected - capturing...")
                continue
            if raw == "PRE_TRIGGER":
                section = "onset"; continue
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
                predict_event()
                section = None
                continue

            # numeric sample line
            try:
                val = int(raw)
            except ValueError:
                continue
            if section == "onset":
                onset.append(val)
            # offset samples ignored - we predict on the onset

    except KeyboardInterrupt:
        print("\nStopping.")
        ser.close()


if __name__ == "__main__":
    main()