#!/usr/bin/env python
"""Waveforms of the five matched S1 <-> long-S2 pairs (one figure per pair).

Both peaks are placed on a common absolute time axis using
``peak_time_ns + (i - sum_ref) * 4 ns`` -- ``peak_time_ns`` is the peak's pulse
start, which is exactly where the sum array index ``sum_ref`` sits."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from muon_analysis.sum_store import load_sum_npz

V2 = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp/muon_analysis/co60_590"
PAIRS = [(593, 38507, 38508), (599, 26889, 26890), (600, 21272, 21273),
         (604, 17266, 17267), (605, 28818, 28819)]

df = pd.read_csv("/mnt/data/tmp/muon_analysis/co60_590/peak_level_v3/co60_590_peak_level_v3.csv")
for rid, s1_id, s2_id in PAIRS:
    st = load_sum_npz(f"{V2}/sum_waveforms/run_{rid:05d}.npz")
    ref = int(st["sum_ref"])
    r1 = df[(df.run_id == rid) & (df.peaks_id == s1_id)].iloc[0]
    r2 = df[(df.run_id == rid) & (df.peaks_id == s2_id)].iloc[0]
    t0 = float(r1.peak_time_ns)

    a1 = np.asarray(st["anode_sums"][s1_id], dtype=float)
    a2 = np.asarray(st["anode_sums"][s2_id], dtype=float)
    d1 = np.asarray(st["dynode_sums"].get(s1_id, np.zeros(0)), dtype=float)
    d2 = np.asarray(st["dynode_sums"].get(s2_id, np.zeros(0)), dtype=float)
    x1 = (np.arange(len(a1)) - ref) * 4 / 1000.0
    x2 = (np.arange(len(a2)) - ref) * 4 / 1000.0
    x2o = x2 + float(r2.peak_time_ns - t0) / 1000.0

    fig, ax = plt.subplots(figsize=(20, 11))
    ax.plot(x1, a1, "royalblue", lw=2.0,
            label=f"S1 id={s1_id}  area={r1.anode_sum_area:.0f} PE  "
                  f"height={r1.height:.0f} ADC  n_ch={int(r1.n_ch)}")
    ax.plot(x2o, a2, "royalblue", lw=1.4,
            label=f"S2 id={s2_id}  area={r2.anode_sum_area:.0f} PE  "
                  f"height={r2.height:.0f} ADC  n_ch={int(r2.n_ch)}  "
                  f"width={r2.width / 1000:.1f} us")
    if d1.size:
        ax.plot((np.arange(len(d1)) - ref) * 4 / 1000.0, -d1, "crimson", ls="--",
                lw=1.1, alpha=0.75, label=f"S1 dynode_sum flipped (len={len(d1)})")
    if d2.size:
        ax.plot((np.arange(len(d2)) - ref) * 4 / 1000.0
                + float(r2.peak_time_ns - t0) / 1000.0, -d2, "crimson",
                ls="--", lw=1.1, alpha=0.75, label=f"S2 dynode_sum flipped (len={len(d2)})")
    dt_us = float(r2.peak_time_ns - t0) / 1000.0
    for x, c, ls, lb in [(0.0, "royalblue", ":", "S1 pulse start"),
                         (dt_us, "gray", ":", f"S2 pulse start (dt={dt_us:.2f} us)")]:
        ax.axvline(x, color=c, ls=ls, lw=2.2, label=lb)
    ax.axhline(0, color="k", lw=0.8, alpha=0.5)
    ax.set_xlabel("t relative to the S1 pulse start  [us]", fontsize=22,
                  fontweight="bold")
    ax.set_ylabel("amplitude  [ADC]", fontsize=22, fontweight="bold")
    ax.grid(True, alpha=0.25)
    ax.legend(fontsize=14, loc="upper right")
    ax.tick_params(labelsize=15)
    fig.suptitle(f"Co60 590+ v2 pair run{rid}: S1 id={s1_id} + long S2 id={s2_id}  "
                 f"(dt = {dt_us:.2f} us, S2 width = {r2.width / 1000:.1f} us)",
                 fontsize=22, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    name = f"co60_590_v2_muon_pair_waveforms_run{rid}.png"
    for o in (f"{DOCS}/{name}", f"{TMP}/{name}"):
        fig.savefig(o, dpi=150)
    plt.close(fig)
    print(f"saved {name}   dt={dt_us:.2f} us  s1_area={r1.anode_sum_area:.1f} PE  "
          f"s2_area={r2.anode_sum_area:.1f} PE")
