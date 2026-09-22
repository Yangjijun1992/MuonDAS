#!/usr/bin/env python
"""30 muon peak-level waveforms whose muon_s2_area_an sits near the n_ch==7 median.

Picks 30 peaks with n_ch == 7 inside +-3% of the median muon_s2_area_an
(25,969 PE) and plots the peak-level sum waveforms with a log y axis
(the amplitude |sum| is shown so a log scale is meaningful)."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.sum_store import load_sum_npz

MED = 25969.0
TOL = 0.03
N_EX = 30
YSCALE = sys.argv[1] if len(sys.argv) > 1 else "log"
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = ("co60_590_v2_muon_s2area25969_peak_waveforms.png" if YSCALE == "log"
        else f"co60_590_v2_muon_s2area25969_peak_waveforms_{YSCALE}.png")

df = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
sel = df[(df.signal_type == "muon") & (df.n_ch == 7)].copy()
sel = sel[(sel.muon_s2_area_an - MED).abs() / MED <= TOL]
sel = sel.sort_values("muon_s2_area_an").reset_index(drop=True)
print(f"n_ch=7 peaks within +-{TOL:.0%} of {MED:g} PE = {len(sel)}")

idx = [int(round(i * (len(sel) - 1) / (N_EX - 1))) for i in range(N_EX)]
picks = sel.iloc[idx]
print(picks[["run_id", "peaks_id", "muon_s2_area_an", "muon_s2_area_dy"]].to_string(index=False))

ncol = 5
nrow = (N_EX + ncol - 1) // ncol
fig, axes = plt.subplots(nrow, ncol, figsize=(4.8 * ncol, 3.3 * nrow))
axes = np.atleast_1d(axes).ravel()
cache = {}
for ax, (_, row) in zip(axes, picks.iterrows()):
    rid = int(row.run_id)
    if rid not in cache:
        cache[rid] = load_sum_npz(f"{TMP}/sum_waveforms/run_{rid:05d}.npz")
    st = cache[rid]
    pid = int(row.peaks_id)
    a = -np.asarray(st["anode_sums"].get(pid, np.zeros(0)), dtype=float)
    dy = np.asarray(st["dynode_sums"].get(pid, np.zeros(0)), dtype=float)
    ref = int(st["sum_ref"])
    ax.plot((np.arange(len(a)) - ref) * 4 / 1000.0, a, "royalblue", lw=0.9,
            label="|anode_sum|")
    if dy.size:
        ax.plot((np.arange(len(dy)) - ref) * 4 / 1000.0, dy, "crimson", ls="--",
                lw=1.0, alpha=0.85, label="|dynode_sum|")
    ax.set_yscale(YSCALE)
    ax.set_title(f"run{rid} id={pid} area_an={row.muon_s2_area_an:.0f} "
                 f"area_dy={row.muon_s2_area_dy:.0f}", fontsize=7)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("t from alignment ref [us]", fontsize=8)
    ax.set_ylabel(f"|ADC| ({YSCALE})", fontsize=8)
    ax.grid(True, alpha=0.2)
    ax.legend(fontsize=6, loc="lower right")

fig.suptitle(f"muon n_ch=7 peaks with muon_s2_area_an within +-{TOL:.0%} of "
             f"{MED:g} PE (n={len(sel)} matching, {N_EX} shown): peak-level waveforms, y {YSCALE}",
             fontsize=14)
fig.tight_layout(rect=(0, 0, 1, 0.98))
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=130)
plt.close(fig)
print("saved", NAME)
