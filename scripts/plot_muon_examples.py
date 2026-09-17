#!/usr/bin/env python
"""Plot 30 muon-classified peak waveforms with the S1-end (== S2-start) marker.

S1 end uses ``find_s1_endpoint_from_peak(..., method="second_derivative")`` (step
3B of docs/muon_s1_s2_cutpoint_algorithm.md).  anode_sum is drawn solid, the
flipped dynode_sum dashed, both aligned at the common sum reference."""
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
from muon_analysis.pulsefinding import (compute_peak_start_end, find_sum_pulse_bounds,
                                        find_s1_endpoint_from_peak)
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

RUN = "00595"
N_EX = 30
MIN_DECAY, MAX_DECAY = 20, 500
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
OUT = f"{TMP}/muon_examples_run595.png"

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
ri = get_runinfo(RUN, cfg["data_source"]["data_root"], runtype="run7_Xe")
rd = read_data(ri, "waveform_analysis_records")
peaks = list(cluster_peaks(match_events(rd, cfg), rd, cfg))
compute_peak_start_end(peaks, rd, cfg)
g = build_gain_db(cfg, run_id=RUN)

csv = pd.read_csv(f"{TMP}/run_{RUN}.csv")
sel = csv[csv.signal_type == "muon"]
ids = [int(i) for i in sel.peaks_id]
print(f"run {RUN}: muon peaks = {len(ids)}")
step = max(1, len(ids) // N_EX)
picks = ids[::step][:N_EX]
by_id = {p.peaks_id: p for p in peaks}

rows = []
for pid in picks:
    pk = by_id.get(pid)
    if pk is None:
        continue
    rows.append((pk, compute_peak_features(pk, rd, g, cfg)))
print(f"plotted = {len(rows)}")

ncol = 5
nrow = (len(rows) + ncol - 1) // ncol
fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 3.1 * nrow))
axes = np.atleast_1d(axes).ravel()
for ax, (pk, pf) in zip(axes, rows):
    s = np.asarray(pf.anode_sum, dtype=float)
    ref = int(pf.sum_ref)
    b = find_sum_pulse_bounds(s, pf.dynode_sum, cfg)
    a_st = b["anode"][0] if "anode" in b else 0
    s1_peak = int(np.argmin(s))
    s1_end = find_s1_endpoint_from_peak(s, s1_peak, MIN_DECAY, MAX_DECAY,
                                        "negative", "second_derivative")
    ax.plot((np.arange(len(s)) - ref) * 4 / 1000.0, s, "royalblue", lw=0.7,
            label="anode_sum")
    if pf.dynode_sum is not None:
        d = -np.asarray(pf.dynode_sum, dtype=float)
        ax.plot((np.arange(len(d)) - ref) * 4 / 1000.0, d, "crimson", ls="--",
                lw=1.0, alpha=0.85, label="dynode_sum (flipped)")
    ax.axvline((s1_peak - ref) * 4 / 1000.0, color="purple", ls=":", lw=1.0,
               label="S1 peak")
    ax.axvline((s1_end - ref) * 4 / 1000.0, color="orange", ls="-.", lw=1.2,
               label="S1 end / S2 start (3B)")
    ax.axhline(0, color="black", ls="--", alpha=0.3, lw=0.5)
    ax.set_title(f"id={pk.peaks_id} nch={len(pk.anode_records)} h={pf.height:.0f} "
                 f"w={pf.width:.0f} w90a={pf.width_90area:.0f} "
                 f"asa={pf.anode_sum_area:.0f} | S1end={(s1_end-a_st)*4:.0f}ns",
                 fontsize=7)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("t from alignment ref [us]", fontsize=8)
    ax.set_ylabel("ADC", fontsize=8)
    ax.legend(fontsize=6, loc="upper right")
for ax in axes[len(rows):]:
    ax.axis("off")
fig.suptitle(f"run {RUN}: muon peaks (n={len(rows)} shown); "
             f"S1 end = 3B 2nd-derivative", fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.98))
fig.savefig(OUT, dpi=130)
plt.close(fig)
print("saved:", OUT)
for pk, pf in rows[:12]:
    s = np.asarray(pf.anode_sum, dtype=float)
    b = find_sum_pulse_bounds(s, pf.dynode_sum, cfg)
    a_st = b["anode"][0] if "anode" in b else 0
    s1_end = find_s1_endpoint_from_peak(s, int(np.argmin(s)), MIN_DECAY, MAX_DECAY,
                                        "negative", "second_derivative")
    print(f"  id={pk.peaks_id} nch={len(pk.anode_records)} h={pf.height:.0f} "
          f"asa={pf.anode_sum_area:.0f} S1end={(s1_end-a_st)*4:.0f}ns")
