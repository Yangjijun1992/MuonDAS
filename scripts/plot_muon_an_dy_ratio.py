#!/usr/bin/env python
"""muon peaks: anode/dynode triggered-channel-count ratio histogram.

n_an_pulse / n_dy_pulse per muon peak, where a channel counts as triggered when
its pulse finder resolved a pulse (pulse_start_sample is not None)."""
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
NAME = "co60_590_v2_muon_an_dy_ratio.png"

d = pd.read_csv(f"{D}/muon_an_dy_channel_ratio.csv")
r = d.ratio.dropna()
print(f"n={len(r)}  median={r.median():.3f}  mean={r.mean():.3f}  "
      f"non-1={((r != 1)).mean()*100:.1f}%")

fig, axes = plt.subplots(1, 2, figsize=(26, 10))

ax = axes[0]
vals, cnts = np.unique(np.round(r, 4), return_counts=True)
ax.bar(vals, cnts, width=0.012, color="royalblue", alpha=0.9)
ax.set_yscale("log")
ax.set_xlabel("n_an_pulse / n_dy_pulse")
ax.set_ylabel("counts (log)")
ax.set_title(f"ratio (n={len(r)}, median={r.median():.3f}, "
             f"=1: {(r == 1).mean()*100:.1f}%)")
ax.grid(True, axis="y", alpha=0.25)

ax = axes[1]
chans = np.arange(0, 9)
ca = [int((d.n_an_pulse == c).sum()) for c in chans]
cd = [int((d.n_dy_pulse == c).sum()) for c in chans]
w = 0.4
ax.bar(chans - w / 2, ca, w, label="anode (pulse found)", color="royalblue")
ax.bar(chans + w / 2, cd, w, label="dynode (pulse found)", color="crimson")
ax.set_yscale("log")
ax.set_xticks(chans)
ax.set_xlabel("triggered channels")
ax.set_ylabel("counts (log)")
ax.set_title("per-side triggered-channel counts")
ax.grid(True, axis="y", alpha=0.25)
ax.legend(framealpha=0.9)

fig.suptitle(f"Co60 590+ v2 muon peaks: anode / dynode triggered-channel ratio "
             f"(n={len(d)})", fontsize=26, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.95))
fig.savefig(f"{DOCS}/{NAME}", dpi=150)
fig.savefig(f"{D}/{NAME}", dpi=150)
plt.close(fig)
print("saved", NAME)
