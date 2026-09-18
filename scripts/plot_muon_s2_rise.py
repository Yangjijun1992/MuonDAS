#!/usr/bin/env python
"""muon_s2 rise-time histogram.

rise = (S2 peak sample - muon_s1_end_sample) * 4 ns, where the S2 peak is the
anode_sum argmin inside the S2 window [muon_s1_end_sample, muon_s2_end_sample]."""
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
NAME = "co60_590_v2_muon_s2_rise.png"

df = pd.read_csv(f"{D}/muon_s1_s2_rise.csv")
v = df.muon_s2_rise_ns
print(f"n={len(v)}  median={v.median():.1f}  q75={v.quantile(.75):.1f} "
      f"q95={v.quantile(.95):.1f}  max={v.max():.1f}  "
      f"zero_frac={(v == 0).mean()*100:.1f}%")

fig, axes = plt.subplots(1, 2, figsize=(26, 10))
lo = df[df.muon_s1_area_an < 2.5e3].muon_s2_rise_ns
hi = df[df.muon_s1_area_an >= 2.5e3].muon_s2_rise_ns

ax = axes[0]
bins = np.arange(0, 201, 4)
ax.hist(v, bins=bins, color="crimson", alpha=0.85)
ax.set_xlabel("muon_s2 rise [ns]")
ax.set_ylabel("counts")
ax.set_title(f"linear x, 0-200 ns (n={len(v)})")
ax.grid(True, axis="y", alpha=0.25)

ax = axes[1]
pos = v[v > 0]
bins = np.logspace(np.log10(pos.min()), np.log10(pos.max()), 80)
ax.hist(lo[lo > 0], bins=bins, color="seagreen", alpha=0.55,
        label=f"area_an < 2.5e3 (n>0: {int((lo>0).sum())})")
ax.hist(hi[hi > 0], bins=bins, color="darkorange", alpha=0.55,
        label=f"area_an >= 2.5e3 (n>0: {int((hi>0).sum())})")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("muon_s2 rise [ns]")
ax.set_ylabel("counts (log)")
ax.set_title("log x / log y, only rise > 0")
ax.grid(True, axis="y", alpha=0.25)
ax.legend(framealpha=0.9)

fig.suptitle(f"Co60 590+ v2 muon peaks: muon_s2 rise "
             f"(s2_peak - muon_s1_end) x 4 ns, n={len(v)}, "
             f"zero = {(v == 0).mean()*100:.1f}%",
             fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig(f"{DOCS}/{NAME}", dpi=150)
fig.savefig(f"{D}/{NAME}", dpi=150)
plt.close(fig)
print("saved", NAME)
