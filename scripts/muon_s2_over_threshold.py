#!/usr/bin/env python
"""Over-threshold statistics of the muon S2 waveform (anode_sum).

For every muon peak whose anode and dynode channels are ALL triggered
(n_an_pulse == 7 and n_dy_pulse == 7) take the anode_sum S2 segment
[muon_s1_end_sample, muon_s2_end_sample), scale every sample by 30, and count
how many samples exceed 1695.  The stored sum waveforms are baseline subtracted."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.sum_store import load_sum_npz

TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_muon_7ch_s2_over1695.png"
SCALE = 30.0
THRESH = 1695.0

ratio = pd.read_csv(f"{TMP}/muon_an_dy_channel_ratio.csv")
df = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
m = df.merge(ratio[(ratio.n_an_pulse == 7) & (ratio.n_dy_pulse == 7)][["run_id", "peaks_id"]],
             on=["run_id", "peaks_id"])
print(f"7ch/7ch muon peaks = {len(m)}")

rows = []
cache = {}
for _, row in m.iterrows():
    rid = int(row.run_id)
    if rid not in cache:
        cache[rid] = load_sum_npz(f"{TMP}/sum_waveforms/run_{rid:05d}.npz")
    store = cache[rid]
    pid = int(row.peaks_id)
    a = np.asarray(store["anode_sums"].get(pid, np.zeros(0)), dtype=float)
    if a.size == 0:
        continue
    ref = int(store["sum_ref"])
    lo = int(row.muon_s1_end_sample) - ref
    hi = int(row.muon_s2_end_sample) - ref
    seg = a[max(lo, 0):max(hi, 0)] * SCALE
    if seg.size == 0:
        continue
    rows.append({"run_id": rid, "peaks_id": pid, "n_points": seg.size,
                 "n_over": int((np.abs(seg) > THRESH).sum()),
                 "n_over_neg": int((seg < -THRESH).sum())})
d = pd.DataFrame(rows)
d["frac_over"] = d.n_over / d.n_points
d.to_csv(f"{TMP}/muon_7ch_s2_over1695.csv", index=False)

tot_pts = int(d.n_points.sum())
tot_over = int(d.n_over.sum())
print(f"waveforms={len(d)}  total points={tot_pts}  over {THRESH:g} (|x30|) = {tot_over} "
      f"({tot_over / tot_pts * 100:.3f}%)")
print(f"  negative-only over threshold = {int(d.n_over_neg.sum())}")
print(f"n_points: min={d.n_points.min()} median={d.n_points.median():.0f} max={d.n_points.max()}")
print(f"n_over  : min={d.n_over.min()} median={d.n_over.median():.0f} max={d.n_over.max()}")
print(f"frac_over: median={d.frac_over.median():.4f} max={d.frac_over.max():.4f}")
print(f"events with n_over>0: {int((d.n_over > 0).sum())} / {len(d)}")

fig, axes = plt.subplots(1, 3, figsize=(30, 9))
panels = [
    (d.n_points, "S2 waveform samples", 120, "royalblue"),
    (d.n_over, f"samples |x{SCALE:g}| > {THRESH:g}", 120, "crimson"),
    (d.frac_over, f"fraction over {THRESH:g}", 120, "seagreen"),
]
for ax, (v, xlab, nb, color) in zip(axes, panels):
    ax.hist(v, bins=nb, color=color, alpha=0.75)
    ax.set_xlabel(xlab, fontsize=20, fontweight="bold")
    ax.set_ylabel("waveforms", fontsize=20, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.25)
    ax.tick_params(labelsize=14)
fig.suptitle(f"muon 7/7 peaks: S2 (anode_sum) over-threshold statistics "
             f"(n={len(d)}, x{SCALE:g}, threshold {THRESH:g}, baseline subtracted)\n"
             f"total points={tot_pts}, over-threshold={tot_over} "
             f"({tot_over / tot_pts * 100:.2f}%)",
             fontsize=20, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.93))
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=150)
plt.close(fig)
print("saved", NAME)
