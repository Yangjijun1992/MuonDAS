#!/usr/bin/env python
"""10 examples of muon 7/7 peaks whose S2 samples above the 1695 ADC threshold
make up more than 80% of the S2 window.

Shows the S2 waveform (anode_sum) with the dynode_sum flipped for comparison and
marks the 1695 ADC threshold."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.sum_store import load_sum_npz

N_EX = 10
THRESH = 1695.0
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_muon_s2over80_dynode_examples.png"

ratio = pd.read_csv(f"{TMP}/muon_an_dy_channel_ratio.csv")
df = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
m = df.merge(ratio[(ratio.n_an_pulse == 7) & (ratio.n_dy_pulse == 7)][["run_id", "peaks_id"]],
             on=["run_id", "peaks_id"])

cache = {}
recs = []
for _, row in m.iterrows():
    rid = int(row.run_id)
    if rid not in cache:
        cache[rid] = load_sum_npz(f"{TMP}/sum_waveforms/run_{rid:05d}.npz")
    st = cache[rid]
    pid = int(row.peaks_id)
    ref = int(st["sum_ref"])
    a = -np.asarray(st["anode_sums"].get(pid, np.zeros(0)), dtype=float)
    lo = max(int(row.muon_s1_end_sample) - ref, 0)
    hi = max(int(row.muon_s2_end_sample) - ref, 0)
    seg = a[lo:hi]
    if seg.size == 0:
        continue
    recs.append({"run_id": rid, "peaks_id": pid, "n_s2": seg.size,
                 "lo": lo, "hi": hi, "frac": float((seg > THRESH).mean())})
d = pd.DataFrame(recs)
sub = d[d.frac > 0.80].sort_values("frac").reset_index(drop=True)
print(f"7/7 muon = {len(d)}   S2 samples > {THRESH:g} ADC over 80% = {len(sub)}")

idx = [int(round(i * (len(sub) - 1) / (N_EX - 1))) for i in range(N_EX)]
picks = sub.iloc[idx]
print(picks[["run_id", "peaks_id", "n_s2", "frac"]].to_string(index=False))

ncol = 5
fig, axes = plt.subplots(2, ncol, figsize=(5.2 * ncol, 7.4))
axes = np.atleast_1d(axes).ravel()
for ax, (_, row) in zip(axes, picks.iterrows()):
    st = cache[int(row.run_id)]
    pid = int(row.peaks_id)
    ref = int(st["sum_ref"])
    a = np.asarray(st["anode_sums"].get(pid, np.zeros(0)), dtype=float)
    dy = np.asarray(st["dynode_sums"].get(pid, np.zeros(0)), dtype=float)
    t = (np.arange(len(a)) - ref) * 4 / 1000.0
    ax.plot(t, a, "royalblue", lw=1.0, label="anode_sum")
    if dy.size:
        ax.plot((np.arange(len(dy)) - ref) * 4 / 1000.0, -dy, "crimson", ls="--",
                lw=1.2, label="dynode_sum (flipped)")
    ax.axhline(-THRESH, color="darkviolet", ls=":", lw=1.6, label=f"-{THRESH:g} ADC")
    ax.set_title(f"run{int(row.run_id)} id={pid} over={row.frac * 100:.1f}% "
                 f"n_S2={int(row.n_s2)}", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.set_xlabel("t from alignment ref [us]", fontsize=9)
    ax.set_ylabel("ADC", fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.legend(fontsize=7, loc="lower right")

fig.suptitle(f"muon 7/7 peaks with S2 samples > {THRESH:g} ADC over 80% "
             f"(n={len(sub)}, 10 shown): S2 waveform", fontsize=15)
fig.tight_layout(rect=(0, 0, 1, 0.96))
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=130)
plt.close(fig)
print("saved", NAME)
