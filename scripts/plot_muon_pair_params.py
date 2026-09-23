#!/usr/bin/env python
"""Parameter profile of the S1 <-> long-S2 pairs found inside the 25 us window.

Marks where each paired S1 / paired S2 sits inside its parent class population."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from muon_analysis.physical_pair import mark_paired_events

V3 = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v3"
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp/muon_analysis/co60_590"
NAME = "co60_590_v2_muon_pair_params.png"
W_US = 10.0

d = pd.read_csv(f"{V3}/co60_590_peak_level_v3.csv")
out, res = mark_paired_events(d, window_ns=25000.0,
                                   s2_width_min_ns=W_US * 1000.0)
p = res["pairs"]
idx = d.set_index(["run_id", "peaks_id"])
s1p = idx.loc[[(int(a), int(b)) for a, b in zip(p.run_id, p.s1_id)]]
s2p = idx.loc[[(int(a), int(b)) for a, b in zip(p.run_id, p.s2_id)]]
s1p.to_csv(f"{TMP}/muon_pair_s1_params.csv")
s2p.to_csv(f"{TMP}/muon_pair_s2_params.csv")

s1all = d[d.signal_type == "S1"]
s2all = d[(d.signal_type == "S2") & (d.width > W_US * 1000.0)]
mu = d[d.signal_type == "muon"]

fig, axes = plt.subplots(1, 3, figsize=(30, 9))

ax = axes[0]
bins = np.logspace(1, 5.5, 120)
ax.hist(s1all.anode_sum_area, bins=bins, color="lightsteelblue", alpha=0.9,
        label=f"S1 class (n={len(s1all)}, med {s1all.anode_sum_area.median():.0f} PE)")
ax.hist(mu.muon_s1_area_an[mu.muon_s1_area_an > 0], bins=bins, color="orange",
        alpha=0.55, label=f"muon S1 segment (med "
                          f"{mu.muon_s1_area_an.median():.0f} PE)")
for v in s1p.anode_sum_area:
    ax.axvline(v, color="red", lw=2.4)
ax.axvline(np.nan, color="red", lw=2.4, label=f"paired S1 (n={len(s1p)})")
ax.set_xscale("log")
ax.set_xlabel("anode_sum_area [PE]")
ax.set_ylabel("counts")
ax.set_title("paired S1 vs S1 populations")
ax.grid(True, alpha=0.25)
ax.legend(fontsize=13)

ax = axes[1]
ax.hist(s2all.anode_sum_area, bins=np.logspace(2, 5.5, 120),
        color="lightcoral", alpha=0.9,
        label=f"long S2 class (n={len(s2all)}, med {s2all.anode_sum_area.median():.0f} PE)")
for v in s2p.anode_sum_area:
    ax.axvline(v, color="darkred", lw=2.4)
ax.axvline(np.nan, color="darkred", lw=2.4, label=f"paired S2 (n={len(s2p)})")
ax.set_xscale("log")
ax.set_xlabel("anode_sum_area [PE]")
ax.set_ylabel("counts")
ax.set_title("paired S2 vs long-S2 class")
ax.grid(True, alpha=0.25)
ax.legend(fontsize=13)

ax = axes[2]
ax.hist(s2all.height, bins=np.logspace(2, 4.5, 120), color="lightcoral",
        alpha=0.9, label=f"long S2 class (med {s2all.height.median():.0f} ADC)")
ax.hist(s1all.height, bins=np.logspace(2, 4.5, 120), color="lightsteelblue",
        alpha=0.7, label=f"S1 class (med {s1all.height.median():.0f} ADC)")
for v in s1p.height:
    ax.axvline(v, color="red", lw=2.4)
for v in s2p.height:
    ax.axvline(v, color="darkred", lw=2.4)
ax.axvline(np.nan, color="red", lw=2.4, label="paired S1")
ax.axvline(np.nan, color="darkred", lw=2.4, label="paired S2")
ax.axvline(15000, color="k", ls="--", lw=2.0, label="height=15000 (S2/muon cut)")
ax.set_xscale("log")
ax.set_xlabel("height [ADC]")
ax.set_ylabel("counts")
ax.set_title("height: paired events vs classes")
ax.grid(True, alpha=0.25)
ax.legend(fontsize=13)

fig.suptitle(f"Co60 590+ v2: parameters of the S1<->long-S2 pairs inside the 25 us window "
             f"(n={len(p)} pairs)", fontsize=24, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.94))
for o in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(o, dpi=150)
plt.close(fig)
print("saved", NAME)
