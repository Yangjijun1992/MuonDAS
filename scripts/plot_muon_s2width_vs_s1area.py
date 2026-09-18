#!/usr/bin/env python
"""Single 2D histogram: muon_s2_width_ns vs muon_s1_area_an (all muon peaks)."""
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

D = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_muon_s2width_vs_s1area.png"

df = pd.read_csv(f"{D}/co60_590_peak_level_v2.csv")
m = df[(df.signal_type == "muon") & (df.muon_s1_height_an < 2e5)]
v = m[(m.muon_s2_width_ns > 0) & (m.muon_s1_area_an > 0)]
print(f"muon={len(m)}  plotted={len(v)}")

xlo, xhi = 1e2, 1e5
ylo, yhi = 1e3, 5e4
fig, ax = plt.subplots(figsize=(18, 13))
hb = ax.hist2d(v.muon_s1_area_an, v.muon_s2_width_ns,
               bins=[np.logspace(np.log10(xlo), np.log10(xhi), 120),
                     np.logspace(np.log10(ylo), np.log10(yhi), 120)],
               cmap="jet", cmin=1, norm=LogNorm())
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(xlo, xhi)
ax.set_ylim(ylo, yhi)
ax.axvline(2.5e3, color="black", ls="--", lw=2.6, label="muon_s1_area_an=2.5e3 PE")
ax.set_xlabel("muon_s1_area_an [PE]")
ax.set_ylabel("muon_s2_width_ns [ns]")
ax.grid(True, alpha=0.15)
cb = fig.colorbar(hb[3], ax=ax)
cb.set_label("counts (log)", fontsize=22, fontweight="bold")
cb.ax.tick_params(labelsize=16)
fig.tight_layout()
fig.savefig(f"{DOCS}/{NAME}", dpi=150)
fig.savefig(f"{D}/{NAME}", dpi=150)
plt.close(fig)
print("saved", NAME)
