#!/usr/bin/env python
"""Split Co60 590+ v2 peak level by the new S1 cut and draw the 4-panel 2D
figure for each side:
    S1  : width_20_50area < 100 ns  AND  width_90area < 1000 ns
    rest: everything else (exceeds either cut)
Outputs co60_590_v2_s1_2d_panels.png and co60_590_v2_nons1_2d_panels.png."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm

CSV = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/co60_590_peak_level_v2_with_signal.csv"
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp"

PANELS = [
    ("width_90area", "width_90area [ns]", (10.0, 1e5), 1000.0),
    ("width_ns", "width_ns [ns]", (40.0, 1e5), 2000.0),
    ("width_20_50area", "width_20_50area [ns]", (1.0, 1e5), 100.0),
    ("height", "height [ADC]", (400.0, 1e6), None),
]


def draw(df, title, out):
    fig, axes = plt.subplots(2, 2, figsize=(24, 20))
    for ax, (col, ylab, ylim, yguide) in zip(axes.ravel(), PANELS):
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
    fig.suptitle(title, fontsize=18)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(out, dpi=150)
    plt.close(fig)
    print("saved:", out)


df = pd.read_csv(CSV)
s1 = df[(df.width_20_50area < 100) & (df.width_90area < 1000)]
rest = df[~((df.width_20_50area < 100) & (df.width_90area < 1000))]
print(f"total={len(df)}  s1={len(s1)}  rest={len(rest)}")

draw(s1, f"Co60 590+ v2 S1 cut (w20_50area<100ns & w90area<1000ns): n={len(s1)}",
     f"{DOCS}/co60_590_v2_s1_2d_panels.png")
draw(rest, f"Co60 590+ v2 NON-S1 (exceeds w20_50area<100ns & w90area<1000ns): n={len(rest)}",
     f"{DOCS}/co60_590_v2_nons1_2d_panels.png")

import shutil
for name in ("co60_590_v2_s1_2d_panels.png", "co60_590_v2_nons1_2d_panels.png"):
    shutil.copy(f"{DOCS}/{name}", f"{TMP}/{name}")
