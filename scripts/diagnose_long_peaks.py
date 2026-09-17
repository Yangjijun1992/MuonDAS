#!/usr/bin/env python
"""Inspect long-peak sum waveforms: where do a_st / end_first / end_final land?
Picks several >5000-sample peaks from run 595 and plots anode_sum + dynode_sum
with the three markers, to diagnose the muon_s1/muon_s2 width definitions."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "axes.labelsize": 24,
    "axes.labelweight": "bold",
    "xtick.labelsize": 17,
    "ytick.labelsize": 17,
    "axes.titlesize": 16,
    "legend.fontsize": 15,
})
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end, find_sum_pulse_bounds
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
ri = get_runinfo("00595", cfg["data_source"]["data_root"], runtype="run7_Xe")
rd = read_data(ri, "waveform_analysis_records")
matched = match_events(rd, cfg)
peaks = list(cluster_peaks(matched, rd, cfg))
compute_peak_start_end(peaks, rd, cfg)
g = build_gain_db(cfg, run_id="00595")

import pandas as pd

rows = []
csv = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/run_00595.csv"
want = pd.read_csv(csv)
want = want[(want.wave_len_samples > 5000) & (want.n_ch == 7)]
want_ids = set(int(i) for i in want.peaks_id)
print(f"CSV long 7ch ids={len(want_ids)}")
for pk in peaks:
    if pk.peaks_id not in want_ids:
        continue
    pf = compute_peak_features(pk, rd, g, cfg)
    rows.append((pk, pf))
rows.sort(key=lambda r: -r[1].wave_len_samples)
print(f"total peaks={len(peaks)}  long 7ch (>5000)={len(rows)}")

picks = rows[:6]
fig, axes = plt.subplots(len(picks), 1, figsize=(16, 3.0 * len(picks)))
if len(picks) == 1:
    axes = [axes]
for ax, (pk, pf) in zip(axes, picks):
    s = pf.anode_sum
    b = find_sum_pulse_bounds(s, pf.dynode_sum, cfg)
    a_st = b["anode"][0] if "anode" in b else 0
    t = (np.arange(len(s)) - a_st) * 4 / 1000.0
    ax.plot(t, s, "b-", lw=0.7, label="anode_sum")
    if pf.dynode_sum is not None and len(pf.dynode_sum) == len(s):
        ax.plot(t, pf.dynode_sum, "r-", lw=0.7, alpha=0.6, label="dynode_sum")
    for x, c, lb in [(a_st, "g", "a_st"), (pf.end_first_sample, "m", "end_first"),
                     (pf.end_final_sample, "k", "end_final")]:
        ax.axvline((x - a_st) * 4 / 1000.0, color=c, ls="--", lw=1.4, label=lb)
    ax.set_title(f"id={pk.peaks_id} n_ch={len(pk.anode_records)} "
                 f"len={pf.wave_len_samples} | S1w={pf.muon_s1_width_ns:.0f}ns "
                 f"S2w={pf.muon_s2_width_ns:.0f}ns width_ns={pf.width_ns:.0f} "
                 f"h={pf.height:.0f}", fontsize=9)
    ax.set_xlabel("time rel. to anode-sum start [us]")
    ax.set_ylabel("anode_sum [ADC]")
    ax.legend(ncol=5, loc="upper right")
fig.tight_layout()
out = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/long_peaks_diagnosis.png"
fig.savefig(out, dpi=120)
print("saved:", out)
for pk, pf in picks:
    print(f"  id={pk.peaks_id} len={pf.wave_len_samples} end_first={pf.end_first_sample} "
          f"end_final={pf.end_final_sample} S1w={pf.muon_s1_width_ns:.0f} "
          f"S2w={pf.muon_s2_width_ns:.0f}")
