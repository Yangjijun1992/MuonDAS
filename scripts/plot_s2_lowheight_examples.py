#!/usr/bin/env python
"""Plot 30 example waveforms for the low-height wide events:
    height < 1.5e4  &  width_90area > 1000  &  anode_sum_area > 300  &  width > 2000
Source run: 00595."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

RUN = "00595"
N_EX = 30
OUT = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/s2_lowheight_examples_run595.png"

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
ri = get_runinfo(RUN, cfg["data_source"]["data_root"], runtype="run7_Xe")
rd = read_data(ri, "waveform_analysis_records")
peaks = list(cluster_peaks(match_events(rd, cfg), rd, cfg))
compute_peak_start_end(peaks, rd, cfg)
g = build_gain_db(cfg, run_id=RUN)

csv = pd.read_csv("/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/run_00595.csv")
sel = csv[(csv.height < 1.5e4) & (csv.width_90area > 1000)
          & (csv.anode_sum_area > 300) & (csv.width > 2000)]
ids = [int(i) for i in sel.peaks_id]
print(f"run {RUN}: matching peaks = {len(ids)}")
step = max(1, len(ids) // N_EX)
picks = ids[::step][:N_EX]
by_id = {p.peaks_id: p for p in peaks}

rows = []
for pid in picks:
    pk = by_id.get(pid)
    if pk is None:
        continue
    pf = compute_peak_features(pk, rd, g, cfg)
    rows.append((pk, pf))
print(f"plotted = {len(rows)}")

ncol, nrow = 5, (len(rows) + 4) // 5
fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 2.9 * nrow))
axes = np.atleast_1d(axes).ravel()
for ax, (pk, pf) in zip(axes, rows):
    s = np.asarray(pf.anode_sum, dtype=float)
    ref = int(pf.sum_ref)
    ax.plot((np.arange(len(s)) - ref) * 4 / 1000.0, s, "royalblue", lw=0.7,
            label="anode_sum")
    if pf.dynode_sum is not None:
        d = -np.asarray(pf.dynode_sum, dtype=float)
        ax.plot((np.arange(len(d)) - ref) * 4 / 1000.0, d, "crimson", ls="--",
                lw=1.0, alpha=0.85, label="dynode_sum (flipped)")
    ax.axvline(0, color="green", ls="--", lw=0.8)
    ax.axhline(0, color="black", ls="--", alpha=0.3, lw=0.5)
    ax.set_title(f"id={pk.peaks_id} nch={len(pk.anode_records)} h={pf.height:.0f} "
                 f"wns={pf.width:.0f} w90a={pf.width_90area:.0f} "
                 f"asa={pf.anode_sum_area:.0f} dsa={pf.dynode_sum_area:.0f}", fontsize=7)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("t from alignment ref [us]", fontsize=8)
    ax.set_ylabel("ADC", fontsize=8)
    ax.legend(fontsize=6, loc="upper right")
for ax in axes[len(rows):]:
    ax.axis("off")
fig.suptitle(f"run {RUN}: height<1.5e4 & width_90area>1000 & anode_sum_area>300 "
             f"& width>2000 (n={len(rows)} shown)", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.98))
fig.savefig(OUT, dpi=130)
plt.close(fig)
print("saved:", OUT)
for pk, pf in rows[:12]:
    print(f"  id={pk.peaks_id} nch={len(pk.anode_records)} h={pf.height:.0f} "
          f"w90a={pf.width_90area:.0f} wns={pf.width:.0f} asa={pf.anode_sum_area:.0f} "
          f"len={pf.wave_len_samples}")
