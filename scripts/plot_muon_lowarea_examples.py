#!/usr/bin/env python
"""Draw 30 example waveforms for muon peaks with muon_s1_area_an < 2.5e3.

Reads the persisted sum-waveform npz (muon_analysis.sum_store) plus the peak
level CSV -- no raw data access needed.  anode_sum is solid, the flipped
dynode_sum dashed, with the muon S1/S2 cut samples and the S1 peak marked."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.sum_store import load_sum_npz

AREA_MAX = 2.5e3
N_EX = 30
ZOOM_US = float(sys.argv[1]) if len(sys.argv) > 1 else None
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
OUT = (f"{TMP}/muon_lowarea_examples_zoom{ZOOM_US:g}us.png" if ZOOM_US
       else f"{TMP}/muon_lowarea_examples.png")

df = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
sel = df[(df.signal_type == "muon") & (df.muon_s1_height_an < 2e5)
         & (df.muon_s1_area_an < AREA_MAX)]
print(f"matching muon peaks = {len(sel)}")
step = max(1, len(sel) // N_EX)
picks = sel.iloc[::step].head(N_EX)
print(f"picked = {len(picks)}, runs = {sorted(picks.run_id.unique().tolist())}")

ncol = 5
nrow = (len(picks) + ncol - 1) // ncol
fig, axes = plt.subplots(nrow, ncol, figsize=(4.6 * ncol, 3.1 * nrow))
axes = np.atleast_1d(axes).ravel()
cache = {}
plotted = 0
for ax, (_, row) in zip(axes, picks.iterrows()):
    rid = int(row.run_id)
    if rid not in cache:
        cache[rid] = load_sum_npz(f"{TMP}/sum_waveforms/run_{rid:05d}.npz")
    store = cache[rid]
    pid = int(row.peaks_id)
    a = np.asarray(store["anode_sums"].get(pid, np.zeros(0)), dtype=float)
    d = np.asarray(store["dynode_sums"].get(pid, np.zeros(0)), dtype=float)
    if a.size == 0:
        ax.axis("off")
        continue
    ref = int(store["sum_ref"])
    lo, mid, hi = (int(row.muon_s1_start_sample), int(row.muon_s1_end_sample),
                   int(row.muon_s2_end_sample))
    s1_peak = int(np.argmin(a))
    t = (np.arange(len(a)) - ref) * 4 / 1000.0
    ax.plot(t, a, "royalblue", lw=0.8, label="anode_sum")
    if d.size:
        ax.plot((np.arange(len(d)) - ref) * 4 / 1000.0, -d, "crimson", ls="--",
                lw=1.0, alpha=0.85, label="dynode_sum (flipped)")
    for x, c, lb, ls in [(s1_peak, "purple", "S1 peak", ":"),
                         (lo, "green", "S1 start", "--"),
                         (mid, "orange", "S1 end / S2 start", "-."),
                         (hi, "black", "S2 end", "--")]:
        ax.axvline((x - ref) * 4 / 1000.0, color=c, ls=ls, lw=0.5, label=lb)
    ax.axhline(0, color="black", ls="--", alpha=0.3, lw=0.5)
    ax.set_title(f"run{rid} id={pid} nch={int(row.n_ch)} "
                 f"asa={row.muon_s1_area_an:.0f} asd={row.muon_s1_area_dy:.0f} "
                 f"h_an={row.muon_s1_height_an:.0f} h_dy={row.muon_s1_height_dy:.0f}",
                 fontsize=7)
    ax.tick_params(labelsize=7)
    if ZOOM_US:
        tpk = (s1_peak - ref) * 4 / 1000.0
        ax.set_xlim(tpk - 0.5, tpk - 0.5 + ZOOM_US)
    ax.set_xlabel("t from alignment ref [us]", fontsize=8)
    ax.set_ylabel("ADC", fontsize=8)
    ax.legend(fontsize=6, loc="upper right")
    plotted += 1
for ax in axes[plotted:]:
    ax.axis("off")
fig.suptitle(f"muon peaks with muon_s1_area_an < {AREA_MAX:g} PE "
             f"(n={plotted} shown)"
             + (f", x zoom = {ZOOM_US:g} us" if ZOOM_US else ""), fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.98))
fig.savefig(OUT, dpi=130)
plt.close(fig)
print("saved:", OUT)
