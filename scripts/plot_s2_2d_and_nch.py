#!/usr/bin/env python
"""S2 anode_sum_area vs dynode_sum_area 2D + n_ch distributions of S1 vs S2."""
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
    "legend.fontsize": 17,
})

CSV = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/co60_590_peak_level_v2_with_signal.csv"
DOCS = "/home/yjj/MuonDAS/docs/figures"
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"

df = pd.read_csv(CSV)
s1 = df[df.signal_type == "S1"]
s2 = df[df.signal_type == "S2"]
print(f"S1={len(s1)}  S2={len(s2)}")

# --- S2: anode_sum_area vs dynode_sum_area ---
v = s2[(s2.dynode_sum_area > 0) & (s2.anode_sum_area > 0)]
lo, hi = 1.0, 1e7
fig, ax = plt.subplots(figsize=(16, 13))
hb = ax.hist2d(v.dynode_sum_area, v.anode_sum_area,
               bins=[np.logspace(np.log10(lo), np.log10(hi), 140)] * 2,
               cmap="jet", cmin=1, norm=LogNorm())
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlim(lo, hi)
ax.set_ylim(lo, hi)
ax.plot([lo, hi], [lo, hi], color="lime", ls=":", lw=2.2, label="y = x")
ax.axhline(300, color="gray", ls="--", lw=2.4, label="anode_sum_area=300 PE")
ax.set_xlabel("dynode_sum_area [PE]")
ax.set_ylabel("anode_sum_area [PE]")
ax.legend(loc="upper left", framealpha=0.9)
cb = fig.colorbar(hb[3], ax=ax)
cb.set_label("counts (log)", fontsize=22, fontweight="bold")
cb.ax.tick_params(labelsize=16)
fig.tight_layout()
fig.savefig(f"{DOCS}/co60_590_v2_s2_anode_vs_dynode_sum_area.png", dpi=150)
fig.savefig(f"{TMP}/co60_590_v2_s2_anode_vs_dynode_sum_area.png", dpi=150)
plt.close(fig)
print(f"saved S2 2D (plotted={len(v)})")

# --- n_ch distribution: S1 vs S2 ---
chans = list(range(1, 8))
c1 = [int((s1.n_ch == c).sum()) for c in chans]
c2 = [int((s2.n_ch == c).sum()) for c in chans]
fig, ax = plt.subplots(figsize=(14, 9))
w = 0.38
xs = np.arange(len(chans))
ax.bar(xs - w / 2, c1, w, label=f"S1 (n={len(s1)})", color="royalblue")
ax.bar(xs + w / 2, c2, w, label=f"S2 (n={len(s2)})", color="crimson")
for x, (a, b) in enumerate(zip(c1, c2)):
    ax.text(x - w / 2, a, f"{a}", ha="center", va="bottom", fontsize=13)
    ax.text(x + w / 2, b, f"{b}", ha="center", va="bottom", fontsize=13)
ax.set_yscale("log")
ax.set_xticks(xs)
ax.set_xticklabels([str(c) for c in chans])
ax.set_xlabel("n_ch")
ax.set_ylabel("counts (log)")
ax.set_title("n_ch distribution: S1 vs S2")
ax.legend(framealpha=0.9)
ax.grid(True, axis="y", alpha=0.25)
fig.tight_layout()
fig.savefig(f"{DOCS}/co60_590_v2_nch_s1_vs_s2.png", dpi=150)
fig.savefig(f"{TMP}/co60_590_v2_nch_s1_vs_s2.png", dpi=150)
plt.close(fig)
print("saved n_ch: S1 =", c1, " S2 =", c2)
