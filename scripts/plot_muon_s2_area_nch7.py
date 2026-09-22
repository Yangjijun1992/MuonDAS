#!/usr/bin/env python
"""muon S2 area histograms for peaks with n_ch == 7.

Separate 1x2 figure: muon_s2_area_an and muon_s2_area_dy (PE) distributions."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams.update({
    "axes.labelsize": 26,
    "axes.labelweight": "bold",
    "xtick.labelsize": 18,
    "ytick.labelsize": 18,
    "axes.titlesize": 22,
    "legend.fontsize": 16,
})

TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_muon_s2_area_nch7.png"

d = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
m = d[(d.signal_type == "muon") & (d.n_ch == 7)]
print(f"muon with n_ch==7 = {len(m)}")

fig, axes = plt.subplots(1, 2, figsize=(26, 10))
for ax, col, color in [(axes[0], "muon_s2_area_an", "royalblue"),
                       (axes[1], "muon_s2_area_dy", "crimson")]:
    v = m[col][m[col] > 0]
    med = v.median()
    ax.hist(v, bins=np.logspace(np.log10(v.min()), np.log10(v.max()), 140),
            color=color, alpha=0.8)
    ax.axvline(med, color="black", ls="--", lw=3.0, label=f"median = {med:.0f} PE")
    ax.set_xscale("log")
    ax.set_xlabel(f"{col} [PE]")
    ax.set_ylabel("Counts")
    ax.set_title(f"{col}  (n={len(v)}, log-log span {np.log10(v.max() / v.min()):.2f} dec)")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right")
fig.suptitle(f"Co60 590+ v2 muon peaks with n_ch = 7: S2 area distributions "
             f"(n={len(m)})", fontsize=24, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.94))
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=150)
plt.close(fig)
print("saved", NAME)
