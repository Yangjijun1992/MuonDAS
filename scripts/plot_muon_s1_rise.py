#!/usr/bin/env python
"""muon_s1 rise-time histogram (all muon peaks).

rise = (S1 peak sample - muon_s1_start_sample) * 4 ns, where the S1 peak is the
anode_sum argmin.  Left panel: linear x (main peak); right panel: log x (tail)."""
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

D = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_muon_s1_rise.png"

df = pd.read_csv(f"{D}/muon_s1_rise.csv")
v = df.muon_s1_rise_ns
print(f"n={len(v)}  median={v.median():.1f}  q25={v.quantile(.25):.1f} "
      f"q75={v.quantile(.75):.1f}  max={v.max():.1f}")

fig, axes = plt.subplots(1, 2, figsize=(26, 10))
lo = df[df.muon_s1_area_an < 2.5e3].muon_s1_rise_ns
hi = df[df.muon_s1_area_an >= 2.5e3].muon_s1_rise_ns

ax = axes[0]
bins = np.arange(0, 101, 2)
ax.hist(v, bins=bins, color="royalblue", alpha=0.85)
ax.set_xlabel("muon_s1 rise [ns]")
ax.set_ylabel("counts")
ax.set_title(f"linear x (n={len(v)})")
ax.grid(True, axis="y", alpha=0.25)

ax = axes[1]
bins = np.logspace(np.log10(max(v.min(), 1)), np.log10(v.max()), 80)
ax.hist(lo, bins=bins, color="seagreen", alpha=0.55,
        label=f"area_an < 2.5e3 (n={len(lo)}, med={lo.median():.0f} ns)")
ax.hist(hi, bins=bins, color="darkorange", alpha=0.55,
        label=f"area_an >= 2.5e3 (n={len(hi)}, med={hi.median():.0f} ns)")
ax.axvline(v.median(), color="black", ls="--", lw=2.2,
           label=f"all median = {v.median():.0f} ns")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("muon_s1 rise [ns]")
ax.set_ylabel("counts (log)")
ax.set_title("log x / log y, split by S1 area")
ax.grid(True, axis="y", alpha=0.25)
ax.legend(framealpha=0.9)

fig.suptitle(f"Co60 590+ v2 muon peaks: muon_s1 rise time "
             f"(s1_peak - muon_s1_start) x 4 ns, n={len(v)}",
             fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig(f"{DOCS}/{NAME}", dpi=150)
fig.savefig(f"{D}/{NAME}", dpi=150)
plt.close(fig)
print("saved", NAME)
