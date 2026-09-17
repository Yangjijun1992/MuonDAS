#!/usr/bin/env python
"""anode_sum_area vs dynode_sum_area for the S1 peaks (Co60 590+ v2)."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

plt.rcParams.update({
    "axes.labelsize": 26,
    "axes.labelweight": "bold",
    "xtick.labelsize": 18,
    "ytick.labelsize": 18,
    "axes.titlesize": 22,
    "legend.fontsize": 16,
})

CSV = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/co60_590_peak_level_v2_with_signal.csv"
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
NAME = "co60_590_v2_s1_anode_vs_dynode_sum_area.png"

df = pd.read_csv(CSV)
s1 = df[df.signal_type == "S1"]
v = s1[(s1.anode_sum_area > 0) & (s1.dynode_sum_area > 0)]
print(f"S1 peaks={len(s1)}  plotted={len(v)}")

lo, hi = 1.0, 1e7
fig, ax = plt.subplots(figsize=(16, 13))
hb = ax.hist2d(
    v.dynode_sum_area, v.anode_sum_area,
    bins=[np.logspace(np.log10(lo), np.log10(hi), 140),
          np.logspace(np.log10(lo), np.log10(hi), 140)],
    cmap="jet", cmin=1, norm=LogNorm())
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(lo, hi)
ax.set_ylim(lo, hi)
ax.plot([lo, hi], [lo, hi], color="lime", ls=":", lw=2.2, label="y = x")
ax.axhline(300, color="gray", ls="--", lw=2.4, label="anode_sum_area=300 PE")
ax.set_xlabel("dynode_sum_area [PE]")
ax.set_ylabel("anode_sum_area [PE]")
ax.set_title(f"Co60 590+ v2 S1 peaks: dynode_sum_area vs anode_sum_area (n={len(v)})")
ax.legend(loc="upper left", framealpha=0.9)
cb = fig.colorbar(hb[3], ax=ax)
cb.set_label("counts (log)", fontsize=22, fontweight="bold")
cb.ax.tick_params(labelsize=16)
fig.tight_layout()
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=150)
plt.close(fig)
print("saved:", f"{TMP}/{NAME}")
