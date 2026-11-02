#!/usr/bin/env python3
"""Collapse every runs/*/ch*.csv into one summary row per cell.

Usage:  python3 analysis/summarize.py
Writes summary.csv in the repo root and prints it.
"""
import glob
import json
import os
import re

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

rows = []
for path in sorted(glob.glob(os.path.join(ROOT, "runs", "*", "ch*.csv"))):
    df = pd.read_csv(path)
    if df.empty:
        continue
    folder = os.path.dirname(path)
    label = os.path.basename(folder)
    meta_path = os.path.join(folder, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            label = json.load(f).get("label", label)
    m = re.match(r"ch(\d+)(?:_(.+))?\.csv", os.path.basename(path))
    rows.append({
        "run": os.path.basename(folder),
        "label": label,
        "channel": int(m.group(1)),
        "cell": m.group(2) or "",
        "mean_temp_C": df["temp_C"].mean(),
        "min_temp_C": df["temp_C"].min(),
        "max_temp_C": df["temp_C"].max(),
        "duration_min": df["time_s"].iloc[-1] / 60,
        "start_V": df["battery_V"].iloc[0],
        "end_V": df["battery_V"].iloc[-1],
        "capacity_mAh": df["capacity_mAh"].iloc[-1],
    })

if not rows:
    raise SystemExit("No data found in runs/.")

out = pd.DataFrame(rows).round(2)
out.to_csv(os.path.join(ROOT, "summary.csv"), index=False)
print(out.to_string(index=False))
