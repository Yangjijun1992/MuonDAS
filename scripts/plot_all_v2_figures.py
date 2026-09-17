#!/usr/bin/env python
"""Regenerate every Co60 590+ v2 figure with larger, high-contrast axis labels.

Outputs to docs/figures/ and /mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/:
  - co60_590_v2_2d_panels.png        (all peaks, 4 panels)
  - co60_590_v2_s1_2d_panels.png     (S1 cut, 4 panels)
  - co60_590_v2_nons1_2d_panels.png  (S2, 4 panels)
  - w2050area_vs_anodesum_area_v2.png
  - width_ns_vs_anodesum_area_v2.png
"""
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
    "axes.titlesize": 20,
    "legend.fontsize": 16,
})

CSV = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/co60_590_peak_level_v2_with_signal.csv"
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"

PANELS = [
    ("width_90area", "width_90area [ns]", (10.0, 1e5), 1000.0),
    ("width_ns", "width_ns [ns]", (40.0, 1e5), 2000.0),
    ("width_20_50area", "width_20_50area [ns]", (1.0, 1e5), 100.0),
    ("height", "height [ADC]", (400.0, 1e6), None),
]


def draw_panels(df, title, name, guides=None):
    guides = guides or {}
    fig, axes = plt.subplots(2, 2, figsize=(24, 20))
    for ax, (col, ylab, ylim, yguide) in zip(axes.ravel(), PANELS):
        g = guides.get(col, yguide)
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
        ax.axvline(300, color="gray", ls="--", lw=2.2, label="anode_sum_area=300 PE")
        if g is not None:
            ax.axhline(g, color="gray", ls="--", lw=2.2, label=f"{col}={g:g}")
        ax.set_xlabel("anode_sum_area [PE]")
        ax.set_ylabel(ylab)
        ax.legend(loc="upper right", framealpha=0.9)
        cb = fig.colorbar(hb[3], ax=ax)
        cb.set_label("counts (log)", fontsize=22, fontweight="bold")
        cb.ax.tick_params(labelsize=16)
    fig.suptitle(title, fontsize=26, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    for out in (f"{DOCS}/{name}", f"{TMP}/{name}"):
        fig.savefig(out, dpi=150)
    plt.close(fig)
    print("saved:", f"{DOCS}/{name}")


def draw_single(df, col, ylab, ylim, yguide, title, name):
    v = df[(df.anode_sum_area > 0) & (df[col] > 0)]
    fig, ax = plt.subplots(figsize=(16, 12))
    hb = ax.hist2d(
        v.anode_sum_area, v[col],
        bins=[np.logspace(np.log10(1.0), np.log10(1e6), 120),
              np.logspace(np.log10(ylim[0]), np.log10(ylim[1]), 120)],
        cmap="jet", cmin=1, norm=LogNorm())
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(1.0, 1e6)
    ax.set_ylim(*ylim)
    ax.axvline(300, color="gray", ls="--", lw=2.4, label="anode_sum_area=300 PE")
    if yguide is not None:
        ax.axhline(yguide, color="gray", ls="--", lw=2.4, label=f"{col}={yguide:g}")
    ax.set_xlabel("anode_sum_area [PE]")
    ax.set_ylabel(ylab)
    ax.set_title(title)
    ax.legend(loc="upper right", framealpha=0.9)
    cb = fig.colorbar(hb[3], ax=ax)
    cb.set_label("counts (log)", fontsize=22, fontweight="bold")
    cb.ax.tick_params(labelsize=16)
    fig.tight_layout()
    for out in (f"{DOCS}/{name}", f"{TMP}/{name}"):
        fig.savefig(out, dpi=150)
    plt.close(fig)
    print("saved:", f"{DOCS}/{name}")


df = pd.read_csv(CSV)
s1 = df[(df.width_20_50area < 100) & (df.width_90area < 1000)]
rest = df[~((df.width_20_50area < 100) & (df.width_90area < 1000))]
cut3 = df[(df.width_ns > 2000) & (df.width_90area > 1000) & (df.height > 1.5e4)]
cut4 = cut3[cut3.n_ch >= 2]
cut_low = df[(df.width_ns > 2000) & (df.width_90area > 1000) & (df.height < 1.5e4)]

draw_panels(df, "Co60 590+ v2 (new clustering + params): peak-level 2D panels",
            "co60_590_v2_2d_panels.png")
draw_panels(s1, f"Co60 590+ v2 S1 cut (w20_50area<100ns & w90area<1000ns): n={len(s1)}",
            "co60_590_v2_s1_2d_panels.png")
draw_panels(rest, f"Co60 590+ v2 S2 (exceeds w20_50area<100ns & w90area<1000ns): n={len(rest)}",
            "co60_590_v2_nons1_2d_panels.png")
draw_panels(cut3, f"Co60 590+ v2 cut: width_ns>2000ns & width_90area>1000ns & height>1.5e4 ADC (n={len(cut3)})",
            "co60_590_v2_wn2000_w90a1000_h15000_2d_panels.png",
            guides={"height": 1.5e4})
draw_panels(cut4, f"Co60 590+ v2 cut: width_ns>2000ns & width_90area>1000ns & height>1.5e4 ADC & n_ch>=2 (n={len(cut4)})",
            "co60_590_v2_wn2000_w90a1000_h15000_nch2_2d_panels.png",
            guides={"height": 1.5e4})
draw_panels(cut_low, f"Co60 590+ v2 cut: width_ns>2000ns & width_90area>1000ns & height<1.5e4 ADC (n={len(cut_low)})",
            "co60_590_v2_wn2000_w90a1000_hlt15000_2d_panels.png",
            guides={"height": 1.5e4})
draw_single(df, "width_20_50area", "width_20_50area [ns]", (1.0, 1e5), 100.0,
            f"Co60 590+ v2: width_20_50area vs anode_sum_area (n={len(df)})",
            "w2050area_vs_anodesum_area_v2.png")
draw_single(df, "width_ns", "width_ns [ns]", (40.0, 1e5), 2000.0,
            f"Co60 590+ v2: width_ns vs anode_sum_area (n={len(df)})",
            "width_ns_vs_anodesum_area_v2.png")
