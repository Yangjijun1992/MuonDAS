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

xlo, xhi = 1e2, 3e5
ylo, yhi = 2e3, 2e5
fig, ax = plt.subplots(figsize=(18, 15))
hb = ax.hist2d(v.muon_s1_area_dy, v.muon_s1_area_an,
               bins=[np.logspace(np.log10(xlo), np.log10(xhi), 120),
                     np.logspace(np.log10(ylo), np.log10(yhi), 120)],
               cmap="jet", cmin=1, norm=LogNorm())
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(xlo, xhi)
ax.set_ylim(ylo, yhi)

ratio = (v.muon_s1_area_dy / v.muon_s1_area_an).median()
gx = np.logspace(np.log10(xlo), np.log10(xhi), 200)
ax.plot(gx, gx, "k--", lw=2.4, label="y = x")
ax.plot(gx, gx / ratio, "w--", lw=2.6, label=f"y = x / {ratio:.3f} (median)")
ax.set_xlabel("muon_s1_area_dy [PE]")
ax.set_ylabel("muon_s1_area_an [PE]")
ax.set_title(f"muon peaks with ALL 7/7 channels triggered (n={len(v)}), "
             f"log-log r = {np.corrcoef(np.log10(v.muon_s1_area_an), np.log10(v.muon_s1_area_dy))[0, 1]:.3f}")
ax.grid(True, alpha=0.15)
ax.legend(loc="upper left", framealpha=0.85)
cb = fig.colorbar(hb[3], ax=ax)
cb.set_label("counts (log)", fontsize=22, fontweight="bold")
cb.ax.tick_params(labelsize=16)
fig.tight_layout()
fig.savefig(f"{DOCS}/{NAME}", dpi=150)
fig.savefig(f"{D}/{NAME}", dpi=150)
plt.close(fig)
print("saved", NAME)
