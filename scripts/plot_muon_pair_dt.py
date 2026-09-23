#!/usr/bin/env python
"""S1<->long-S2 pairing: dt of the matched pairs and the underlying timing structure.

Left  : dt of every successfully matched S1/long-S2 pair (25 us window).
Right : for every long S2, the dt to the nearest preceding S1 (log-log) -- shows
        the real tens-of-ms separation that makes the 25 us window essentially
        empty except for random coincidences."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from muon_analysis.physical_pair import mark_paired_muon_events

V3 = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v3"
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp/muon_analysis/co60_590"
NAME = "co60_590_v2_muon_pair_dt.png"
WINDOW_US = 25.0
W_US = 15.0

d = pd.read_csv(f"{V3}/co60_590_peak_level_v3.csv")
out, res = mark_paired_muon_events(d, window_ns=WINDOW_US * 1000.0,
                                   s2_width_min_ns=W_US * 1000.0)
p = res["pairs"].copy()
p["dt_us"] = p.dt_ns / 1000.0
p["inside"] = p.dt_us < p.s2_width_ns / 1000.0
p.to_csv(f"{TMP}/muon_pair_dt.csv", index=False)
print(p[["run_id", "s1_id", "s2_id", "dt_us", "s1_size", "s2_size",
         "s2_width_ns", "inside"]].to_string(index=False))
print(f"\npaired n={len(p)}  dt_us: {sorted(p.dt_us.round(2).tolist())}")
print(f"  S1 falls inside the S2 span: {int(p.inside.sum())}/{len(p)}")

s1 = d[d.signal_type == "S1"]
s2 = d[(d.signal_type == "S2") & (d.width > W_US * 1000.0)]
near = []
for rid, g in s2.groupby("run_id"):
    t1 = np.sort(s1[s1.run_id == rid].peak_time_ns.to_numpy())
    for t in np.sort(g.peak_time_ns.to_numpy()):
        i = np.searchsorted(t1, t, side="left") - 1
        if i >= 0:
            near.append((t - t1[i]) / 1000.0)
near = np.asarray(near)
print(f"nearest-preceding-S1 dt (n={len(near)}): median={np.median(near):.0f} us, "
      f"<{WINDOW_US:g}us = {(near < WINDOW_US).mean() * 100:.4f}%")

fig, axes = plt.subplots(1, 2, figsize=(28, 10))

ax = axes[0]
ax.stem(p.dt_us, np.arange(len(p)), linefmt="C0-", markerfmt="o", basefmt="k-")
ax.set_yticks(np.arange(len(p)))
ax.set_yticklabels([f"run{int(r)}  S2={w / 1000:.1f}us"
                    for r, w in zip(p.run_id, p.s2_width_ns)], fontsize=15)
ax.axvline(WINDOW_US, color="k", ls="--", lw=2.4,
           label=f"pairing window {WINDOW_US:g} us")
ax.set_xlabel("dt  (S2 start - S1 start)  [us]", fontsize=22, fontweight="bold")
ax.set_xlim(0, WINDOW_US * 1.12)
ax.grid(True, alpha=0.25)
ax.legend(fontsize=16)
ax.set_title(f"matched S1 - long-S2 pairs (n={len(p)}, S2 width > {W_US:g} us)\n"
             f"dt median = {p.dt_us.median():.2f} us", fontsize=20)

ax = axes[1]
bins = np.logspace(np.log10(max(near.min(), 1e-2)), np.log10(near.max()), 160)
ax.hist(near, bins=bins, color="seagreen", alpha=0.85)
ax.axvline(WINDOW_US, color="k", ls="--", lw=2.4,
           label=f"pairing window {WINDOW_US:g} us")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("dt to nearest preceding S1  [us]", fontsize=22, fontweight="bold")
ax.set_ylabel("long S2 count (log)", fontsize=22, fontweight="bold")
ax.grid(True, alpha=0.25)
ax.legend(fontsize=16)
ax.set_title(f"all long S2 (n={len(near)}): median dt = {np.median(near):,.0f} us "
             f"-- only {(near < WINDOW_US).mean() * 100:.4f}% within {WINDOW_US:g} us",
             fontsize=20)

fig.suptitle("Co60 590+ v2: S1 <-> long-S2 pairing timing",
             fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.94))
for o in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(o, dpi=150)
plt.close(fig)
print("saved", NAME)
