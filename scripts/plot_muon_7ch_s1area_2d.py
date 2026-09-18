#!/usr/bin/env python
"""2D histogram: muon_s1_area_an vs muon_s1_area_dy for muon peaks whose anode
AND dynode channels are ALL triggered (n_an_pulse == 7 and n_dy_pulse == 7)."""
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
NAME = "co60_590_v2_muon_7ch_s1area_dy_vs_an.png"

df = pd.read_csv(f"{D}/co60_590_peak_level_v2.csv")
r = pd.read_csv(f"{D}/muon_an_dy_channel_ratio.csv")
m = df.merge(r[(r.n_an_pulse == 7) & (r.n_dy_pulse == 7)][["run_id", "peaks_id"]],
             on=["run_id", "peaks_id"])
v = m[(m.muon_s1_area_an > 0) & (m.muon_s1_area_dy > 0)]
print(f"7ch/7ch muon peaks={len(m)}  plotted={len(v)}")

xlo, xhi = 1e3, 3e5
ylo, yhi = 2e3, 4e4
fig, ax = plt.subplots(figsize=(18, 15))
hb = ax.hist2d(v.muon_s1_area_dy, v.muon_s1_area_an,
               bins=[np.logspace(np.log10(xlo), np.log10(xhi), 120),
                     np.logspace(np.log10(ylo), np.log10(yhi), 120)],
               cmap="jet", cmin=1, norm=LogNorm())
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(xlo, xhi)
ax.set_ylim(ylo, yhi)

FIT_LO, FIT_HI = 1e3, 4e3
fit = v[(v.muon_s1_area_dy >= FIT_LO) & (v.muon_s1_area_dy <= FIT_HI)]
k = 10 ** np.mean(np.log10(fit.muon_s1_area_an / fit.muon_s1_area_dy))
print(f"y=kx fit on muon_s1_area_dy in [{FIT_LO:g},{FIT_HI:g}]: n={len(fit)}  k={k:.4f} "
      f"(median y/x={np.median(fit.muon_s1_area_an / fit.muon_s1_area_dy):.4f})")

gx = np.logspace(np.log10(xlo), np.log10(xhi), 200)
ax.plot(gx, gx, color="0.5", ls=":", lw=2.0, label="y = x (reference)")
gxf = np.logspace(np.log10(FIT_LO), np.log10(FIT_HI), 50)
ax.plot(gxf, k * gxf, "k--", lw=3.4, label=f"y = {k:.3f} x")
ax.set_xlabel("muon_s1_area_dy [PE]")
ax.set_ylabel("muon_s1_area_an [PE]")
ax.set_title(f"muon peaks with ALL 7/7 channels triggered (n={len(v)}), "
             f"log-log r = {np.corrcoef(np.log10(v.muon_s1_area_an), np.log10(v.muon_s1_area_dy))[0, 1]:.3f}")
ax.grid(True, alpha=0.15)
for sp in ax.spines.values():
    sp.set_linewidth(3.0)
ax.tick_params(width=3.0, length=10)
ax.legend(loc="upper left", framealpha=0.85)
cb = fig.colorbar(hb[3], ax=ax)
cb.set_label("counts (log)", fontsize=22, fontweight="bold")
cb.ax.tick_params(labelsize=16)
fig.tight_layout()
fig.savefig(f"{DOCS}/{NAME}", dpi=150)
fig.savefig(f"{D}/{NAME}", dpi=150)
plt.close(fig)
print("saved", NAME)
