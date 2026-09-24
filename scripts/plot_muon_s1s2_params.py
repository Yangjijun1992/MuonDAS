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
def draw_2d(data, name, title):
    fig, axes = plt.subplots(2, 3, figsize=(36, 20))
    grid = [(axes[0, k], spec) for k, spec in enumerate(panels_s1)]
    grid += [(axes[1, k], spec) for k, spec in enumerate(panels_row2)]
    for ax, (xc, yc, xlab, ylab) in grid:
        v = data[(data[xc] > 0) & (data[yc] > 0)]
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
    fig.suptitle(title, fontsize=26, fontweight="bold")
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    fig.savefig(f"{DOCS}/{name}", dpi=150)
    fig.savefig(f"{TMP}/{name}", dpi=150)
    plt.close(fig)
    print(f"saved {name}")


draw_2d(m, "co60_590_v2_muon_s1s2_2d.png",
        f"Co60 590+ v2 muon peaks: S1/S2 parameter correlations (n={len(m)})")
lo = m[m.muon_s1_area_an < 2.5e3]
draw_2d(lo, "co60_590_v2_muon_s1s2_2d_lowarea.png",
        f"Co60 590+ v2 muon peaks with muon_s1_area_an < 2.5e3: "
        f"S1/S2 parameter correlations (n={len(lo)})")

# --- Figure 3: light intensity (area / width) histograms ---
N_PMT = 7.0
SCALE_S2 = 46.9
s1_raw = (m["muon_s1_area_an"] / m["muon_s1_width_ns"])
s1_raw = s1_raw.replace([np.inf, -np.inf], np.nan).dropna()
s1_raw = s1_raw[s1_raw > 0]
s2_raw = (m["muon_s2_area_an"] / m["muon_s2_width_ns"])
s2_raw = s2_raw.replace([np.inf, -np.inf], np.nan).dropna()
s2_raw = s2_raw[s2_raw > 0]
s2_int = s2_raw / N_PMT * SCALE_S2
def draw_intensity(name):
    fig, ax = plt.subplots(figsize=(18, 11))
    curves = [
        (s1_raw / N_PMT, "royalblue", "muon_s1 /7", "stepfilled", 0.55),
        (s2_raw / N_PMT, "crimson", "muon_s2 /7", "stepfilled", 0.55),
        (s2_int, "darkorange", f"muon_s2 /7 x{SCALE_S2:g}", "step", 1.0),
    ]
    for v, color, lab, htype, alpha in curves:
        bins = np.logspace(np.log10(v.min()), np.log10(v.max()), 90)
        ax.hist(v, bins=bins, color=color, alpha=alpha, histtype=htype, lw=2.4,
                label=lab)
    for x, color in [(10.0, "darkviolet"), (500.0, "red"), (1000.0, "darkgreen")]:
        ax.axvline(x, color=color, ls="--", lw=2.6, label=f"{x:g} PE/ns/PMT")
    ax.set_xscale("log")
    ax.set_xlim(1e-2, 1.5e3)
    ax.set_xlabel("Intensity [PE/ns/PMT]")
    ax.set_ylabel("counts")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend(framealpha=0.9)
    fig.tight_layout()
    fig.savefig(f"{DOCS}/{name}", dpi=150)
    fig.savefig(f"{TMP}/{name}", dpi=150)
    plt.close(fig)
    print(f"saved {name}")


draw_intensity("co60_590_v2_muon_s1s2_intensity_liny.png")

fig, axes = plt.subplots(1, 2, figsize=(26, 10))
for ax, col, color in [(axes[0], "muon_s2_area_an", "royalblue"),
                       (axes[1], "muon_s2_area_dy", "crimson")]:
    v = m[col][m[col] > 0]
    med = v.median()
    ax.hist(v, bins=np.logspace(np.log10(v.min()), np.log10(v.max()), 140),
            color=color, alpha=0.85)
    ax.axvline(med, color="black", ls="--", lw=3.0, label=f"median = {med:.0f} PE")
    ax.set_xscale("log")
    ax.set_xlabel(f"{col} [PE]")
    ax.set_ylabel("counts")
    ax.set_title(f"{col}  (n={len(v)})")
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper right")
fig.suptitle(f"Co60 590+ v2 muon peaks: S2 segment area distributions (n={len(m)})",
             fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.94))
for out in (f"{DOCS}/co60_590_v2_muon_s2_area.png",
            f"{TMP}/co60_590_v2_muon_s2_area.png"):
    fig.savefig(out, dpi=150)
plt.close(fig)
print("saved co60_590_v2_muon_s2_area.png")
