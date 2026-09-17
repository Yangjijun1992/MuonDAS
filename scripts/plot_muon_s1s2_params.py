#!/usr/bin/env python
"""muon S1/S2 parameter distributions and correlations (Co60 590+ v2).

Figure 1: 1D histograms of muon_s1_width_ns, muon_s2_width_ns,
          muon_s1_height_an, muon_s1_height_dy.
Figure 2: 2D histograms of muon_s1_height_an vs muon_s1_area_an,
          muon_s2_width_ns vs muon_s2_area_an,
          muon_s1_height_dy vs muon_s1_height_an,
          muon_s1_area_an vs muon_s1_area_dy.
Only peaks labelled "muon" are used."""
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

CSV = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/co60_590_peak_level_v2.csv"
HEIGHT_AN_MAX = 2.0e5
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"

df = pd.read_csv(CSV)
m = df[df.signal_type == "muon"]
m = m[m.muon_s1_height_an < 2.0e5]
print(f"muon peaks = {len(m)} (after muon_s1_height_an < 2e5)")

# --- Figure 1: 1D histograms ---
panels1 = [
    ("muon_s1_width_ns", "muon_s1_width_ns [ns]", None),
    ("muon_s2_width_ns", "muon_s2_width_ns [ns]", None),
    ("muon_s1_height_an", "muon_s1_height_an [ADC]", "log"),
    ("muon_s1_height_dy", "muon_s1_height_dy [ADC]", "log"),
]
fig, axes = plt.subplots(2, 2, figsize=(22, 16))
for ax, (col, lab, xlog) in zip(axes.ravel(), panels1):
    v = m[col]
    v = v[v > 0]
    if xlog == "log":
        bins = np.logspace(np.log10(max(v.min(), 1)), np.log10(v.max()), 80)
    else:
        bins = 80
    ax.hist(v, bins=bins, color="royalblue", alpha=0.85)
    if xlog == "log":
        ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel(lab)
    ax.set_ylabel("counts (log)")
    ax.set_title(f"{col}  (n={len(v)}, median={v.median():,.1f})")
    ax.grid(True, axis="y", alpha=0.25)
fig.suptitle(f"Co60 590+ v2 muon peaks: S1/S2 width and height (n={len(m)})",
             fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.97))
fig.savefig(f"{DOCS}/co60_590_v2_muon_s1s2_1d.png", dpi=150)
fig.savefig(f"{TMP}/co60_590_v2_muon_s1s2_1d.png", dpi=150)
plt.close(fig)
print("saved 1D")

# --- Figure 2: 2D histograms ---
panels_s1 = [
    ("muon_s1_area_an", "muon_s1_height_an",
     "muon_s1_area_an [PE]", "muon_s1_height_an [ADC]"),
    ("muon_s1_height_dy", "muon_s1_height_an",
     "muon_s1_height_dy [ADC]", "muon_s1_height_an [ADC]"),
    ("muon_s1_area_an", "muon_s1_width_ns",
     "muon_s1_area_an [PE]", "muon_s1_width_ns [ns]"),
]
panels_row2 = [
    ("muon_s1_area_dy", "muon_s1_area_an",
     "muon_s1_area_dy [PE]", "muon_s1_area_an [PE]"),
    ("muon_s2_area_an", "muon_s2_width_ns",
     "muon_s2_area_an [PE]", "muon_s2_width_ns [ns]"),
    ("muon_s2_area_an", "muon_s2_height_an",
     "muon_s2_area_an [PE]", "muon_s2_height_an [ADC]"),
]
fig, axes = plt.subplots(2, 3, figsize=(36, 20))
grid = [(axes[0, k], spec) for k, spec in enumerate(panels_s1)]
grid += [(axes[1, k], spec) for k, spec in enumerate(panels_row2)]
for ax, (xc, yc, xlab, ylab) in grid:
    v = m[(m[xc] > 0) & (m[yc] > 0)]
    xlo = 10 ** np.floor(np.log10(v[xc].min()))
    ylo = 10 ** np.floor(np.log10(v[yc].min()))
    xhi = HEIGHT_AN_MAX if xc == "muon_s1_height_an" else 10 ** np.ceil(np.log10(v[xc].max()))
    yhi = HEIGHT_AN_MAX if yc == "muon_s1_height_an" else 10 ** np.ceil(np.log10(v[yc].max()))
    hb = ax.hist2d(v[xc], v[yc],
                   bins=[np.logspace(np.log10(xlo), np.log10(xhi), 100),
                         np.logspace(np.log10(ylo), np.log10(yhi), 100)],
                   cmap="jet", cmin=1, norm=LogNorm())
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(xlo, xhi)
    ax.set_ylim(ylo, yhi)
    ax.set_xlabel(xlab)
    ax.set_ylabel(ylab)
    ax.grid(True, alpha=0.15)
    cb = fig.colorbar(hb[3], ax=ax)
    cb.set_label("counts (log)", fontsize=22, fontweight="bold")
    cb.ax.tick_params(labelsize=16)
fig.suptitle(f"Co60 590+ v2 muon peaks: S1/S2 parameter correlations (n={len(m)})",
             fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.98))
fig.savefig(f"{DOCS}/co60_590_v2_muon_s1s2_2d.png", dpi=150)
fig.savefig(f"{TMP}/co60_590_v2_muon_s1s2_2d.png", dpi=150)
plt.close(fig)
print("saved 2D")

# --- Figure 3: light intensity (area / width) histograms ---
intensity = [
    ("muon_s1", "muon_s1_area_an", "muon_s1_width_ns", "royalblue"),
    ("muon_s2", "muon_s2_area_an", "muon_s2_width_ns", "crimson"),
]
fig, axes = plt.subplots(1, 2, figsize=(26, 10))
for ax, (lbl, ac, wc, color) in zip(axes, intensity):
    v = (m[ac] / m[wc]).replace([np.inf, -np.inf], np.nan).dropna()
    v = v[v > 0]
    bins = np.logspace(np.log10(v.min()), np.log10(v.max()), 90)
    ax.hist(v, bins=bins, color=color, alpha=0.85)
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.axvline(v.median(), color="black", ls="--", lw=2.0,
               label=f"median = {v.median():.3f} PE/ns")
    ax.set_xlabel(f"{lbl} intensity [PE/ns]  (area_an / width_ns)")
    ax.set_ylabel("counts (log)")
    ax.set_title(f"{lbl}: light intensity = {ac} / {wc}  (n={len(v)})")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(framealpha=0.9)
fig.suptitle(f"Co60 590+ v2 muon peaks: S1/S2 light intensity "
             f"(area_an / width_ns), n={len(m)}", fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig(f"{DOCS}/co60_590_v2_muon_s1s2_intensity.png", dpi=150)
fig.savefig(f"{TMP}/co60_590_v2_muon_s1s2_intensity.png", dpi=150)
plt.close(fig)
print("saved intensity")
