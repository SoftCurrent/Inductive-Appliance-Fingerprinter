#!/usr/bin/env python3
"""
Inductive Appliance Fingerprinter - Stage 2: feature extraction.

Reads data/manifest.csv and, for every captured event, computes a row
of shape-based features from its onset transient and steady-state log.
Writes data/features.csv - one row per event, ready for a classifier.

Design note: the onset transient is time-stretched by the serial
bottleneck, so every feature here is SHAPE-based (ratios, harmonics,
envelope) rather than absolute-time-based. Harmonic features assume the
waveform is periodic at the mains fundamental, which holds regardless of
the exact stretch, because we detect the period from the data itself.

Usage:
    python extract_features.py
Requires: numpy   ->   pip install numpy
"""

import csv
import os
import sys

try:
    import numpy as np
except ImportError:
    sys.exit("numpy not installed. Run: pip install numpy")

DATA_DIR = "data"
MANIFEST = os.path.join(DATA_DIR, "manifest.csv")
OUT      = os.path.join(DATA_DIR, "features.csv")


def load_samples(path):
    """Load a one-column CSV of integer samples (offset already removed)."""
    if not path or not os.path.exists(path):
        return np.array([])
    vals = []
    with open(path) as f:
        r = csv.reader(f)
        next(r, None)  # header
        for row in r:
            if row:
                try:
                    vals.append(float(row[0]))
                except ValueError:
                    pass
    return np.array(vals)


def estimate_period(sig, fs_guess=10000, f_line=50):
    """Estimate samples-per-cycle via autocorrelation, so we don't rely
    on the (stretched) nominal sample rate. Returns period in samples."""
    if len(sig) < 200:
        return None
    sig = sig - sig.mean()
    # Search a plausible range around the nominal period.
    nominal = fs_guess / f_line          # e.g. 200 samples/cycle
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
    """Ratios of harmonics 2..n_harm to the fundamental, via a single-
    cycle-aligned FFT. Robust to time-stretch because 'period' is measured."""
    if period is None or len(sig) < period * 4:
        return [0.0] * (n_harm - 1) + [0.0]  # ratios + THD
    # Use an integer number of cycles for a clean spectrum.
    n_cycles = len(sig) // period
    usable = sig[: n_cycles * period]
    spec = np.abs(np.fft.rfft(usable - usable.mean()))
    # The fundamental bin corresponds to n_cycles (one full wave per cycle).
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
    """Inrush ratio and settling behaviour from the amplitude envelope."""
    if period is None or len(sig) < period * 3:
        return 0.0, 0.0
    n_cycles = len(sig) // period
    # RMS per cycle -> the envelope.
    env = np.array([rms(sig[i * period:(i + 1) * period])
                    for i in range(n_cycles)])
    if len(env) < 3 or env[-1] < 1e-9:
        return 0.0, 0.0
    steady = np.median(env[-max(3, len(env) // 4):])  # last quarter
    if steady < 1e-9:
        return 0.0, 0.0
    inrush_ratio = float(env.max() / steady)
    # Settling: cycles until env stays within 20% of steady.
    settle = len(env)
    for i in range(len(env)):
        if abs(env[i] - steady) / steady < 0.20:
            settle = i
            break
    settle_frac = float(settle / len(env))
    return inrush_ratio, settle_frac


def steady_features(path):
    """Mean and coefficient-of-variation of steady RMS, plus duration."""
    if not path or not os.path.exists(path):
        return 0.0, 0.0, 0
    rms_vals = []
    with open(path) as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) >= 1:
                try:
                    rms_vals.append(float(row[0]))
                except ValueError:
                    pass
    if not rms_vals:
        return 0.0, 0.0, 0
    arr = np.array(rms_vals)
    mean = float(arr.mean())
    cov = float(arr.std() / mean) if mean > 1e-9 else 0.0
    return mean, cov, len(arr)


def main():
    if not os.path.exists(MANIFEST):
        sys.exit(f"No manifest at {MANIFEST}. Capture some events first.")

    rows = []
    with open(MANIFEST) as f:
        for m in csv.DictReader(f):
            onset = load_samples(os.path.join(DATA_DIR, m["onset_file"]))
            if len(onset) < 400:
                print(f"  skipping event {m['event_id']} - onset too short")
                continue

            period = estimate_period(onset)
            crest = (np.abs(onset).max() / rms(onset)) if rms(onset) > 0 else 0.0
            inrush, settle = envelope_features(onset, period)
            harm = harmonic_ratios(onset, period)      # 6 ratios + THD
            s_mean, s_cov, s_dur = steady_features(
                os.path.join(DATA_DIR, m["steady_file"]))

            rows.append({
                "event_id": m["event_id"],
                "label": m["label"],
                "onset_crest": round(crest, 3),
                "inrush_ratio": round(inrush, 3),
                "settle_frac": round(settle, 3),
                "h2": round(harm[0], 4),
                "h3": round(harm[1], 4),
                "h4": round(harm[2], 4),
                "h5": round(harm[3], 4),
                "h6": round(harm[4], 4),
                "h7": round(harm[5], 4),
                "thd": round(harm[6], 4),
                "steady_rms": round(s_mean, 2),
                "steady_cov": round(s_cov, 4),
                "steady_dur": s_dur,
            })

    if not rows:
        sys.exit("No usable events found.")

    fields = list(rows[0].keys())
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    print(f"\nWrote {len(rows)} events to {OUT}")
    # Quick per-label summary so you can eyeball separation as you go.
    labels = {}
    for r in rows:
        labels.setdefault(r["label"], []).append(r)
    print("\nPer-device averages (a quick sanity check):")
    print(f"{'label':<16}{'n':>4}{'inrush':>9}{'crest':>8}{'h3':>8}{'thd':>8}")
    for lab, rs in sorted(labels.items()):
        n = len(rs)
        inr = np.mean([r["inrush_ratio"] for r in rs])
        cr  = np.mean([r["onset_crest"] for r in rs])
        h3  = np.mean([r["h3"] for r in rs])
        td  = np.mean([r["thd"] for r in rs])
        print(f"{lab:<16}{n:>4}{inr:>9.2f}{cr:>8.2f}{h3:>8.3f}{td:>8.3f}")


if __name__ == "__main__":
    main()