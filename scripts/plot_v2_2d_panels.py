#!/usr/bin/env python
"""Four 2D panels (separate axes) vs anode_sum_area, Co60 590+ v2 data:
width_90area, width_ns, width_20_50area, height."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

CSV = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/co60_590_peak_level_v2_with_signal.csv"
OUT = "/home/yjj/MuonDAS/docs/figures/co60_590_v2_2d_panels.png"

df = pd.read_csv(CSV)
panels = [
    ("width_90area", "width_90area [ns]", (1.0, 1e5), None),
    ("width_ns", "width_ns [ns]", (1e1, 1e5), 2000.0),
    ("width_20_50area", "width_20_50area [ns]", (1.0, 1e5), 80.0),
    ("height", "height [ADC]", (1e1, 1e6), None),
]

fig, axes = plt.subplots(2, 2, figsize=(24, 20))
for ax, (col, ylab, ylim, yguide) in zip(axes.ravel(), panels):
    v = df[(df.anode_sum_area > 0) & (df[col] > 0)]
    hb = ax.hist2d(
        v.anode_sum_area, v[col],
        bins=[np.logspace(np.log10(1.0), np.log10(1e6), 120),
              np.logspace(np.log10(ylim[0]), np.log10(ylim[1]), 120)],
        cmap="jet", cmin=1, norm=LogNorm())
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1.0, 1e6)
    ax.set_ylim(*ylim)
    ax.axvline(300, color="gray", ls="--", lw=1.8, label="anode_sum_area=300 PE")
    if yguide is not None:
        ax.axhline(yguide, color="gray", ls="--", lw=1.8, label=f"{col}={yguide:g}")
    ax.set_xlabel("anode_sum_area [PE]", fontsize=16)
    ax.set_ylabel(ylab, fontsize=16)
    ax.set_title(f"{col} vs anode_sum_area (n={len(v)})", fontsize=14)
    ax.tick_params(labelsize=13)
    ax.legend(fontsize=12)
    cb = fig.colorbar(hb[3], ax=ax)
    cb.set_label("counts (log)", fontsize=14)
    cb.ax.tick_params(labelsize=11)

fig.suptitle("Co60 590+ v2 (new clustering + params): peak-level 2D panels", fontsize=18)
fig.tight_layout(rect=(0, 0, 1, 0.98))
fig.savefig(OUT, dpi=150)
print("saved:", OUT)
