#!/usr/bin/env python
"""10 example muon 7/7 peaks whose S2 over-threshold fraction exceeds 80%.

Plots the dynode_sum waveform (flipped, dashed) together with the anode_sum for
reference, plus the S2 window edges.  Waveforms come from the persisted npz."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.sum_store import load_sum_npz

N_EX = 10
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_muon_s2over80_dynode_examples.png"

over = pd.read_csv(f"{TMP}/muon_7ch_s2_over1695.csv")
df = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
m = df.merge(over[over.frac_over_an > 0.80][["run_id", "peaks_id", "frac_over_an"]],
             on=["run_id", "peaks_id"]).sort_values("frac_over_an").reset_index(drop=True)
print(f"frac_over_an > 0.80 的事例 = {len(m)}")

idx = [int(round(i * (len(m) - 1) / (N_EX - 1))) for i in range(N_EX)]
picks = m.iloc[idx]
print(picks[["run_id", "peaks_id", "frac_over_an"]].to_string(index=False))

ncol = 5
fig, axes = plt.subplots(2, ncol, figsize=(5.0 * ncol, 7.0))
axes = np.atleast_1d(axes).ravel()
cache = {}
for ax, (_, row) in zip(axes, picks.iterrows()):
    rid = int(row.run_id)
    if rid not in cache:
        cache[rid] = load_sum_npz(f"{TMP}/sum_waveforms/run_{rid:05d}.npz")
    st = cache[rid]
    pid = int(row.peaks_id)
    ref = int(st["sum_ref"])
    a = np.asarray(st["anode_sums"].get(pid, np.zeros(0)), dtype=float)
    dy = np.asarray(st["dynode_sums"].get(pid, np.zeros(0)), dtype=float)
    t = (np.arange(len(a)) - ref) * 4 / 1000.0
    ax.plot(t, a, "royalblue", lw=1.0, label="anode_sum")
    if dy.size:
        ax.plot((np.arange(len(dy)) - ref) * 4 / 1000.0, dy, "crimson", ls="--",
                lw=1.2, label="dynode_sum")
    lo = (int(row.muon_s1_end_sample) - ref) * 4 / 1000.0
    hi = (int(row.muon_s2_end_sample) - ref) * 4 / 1000.0
    ax.axvline(lo, color="orange", ls="-.", lw=1.2, label="S1 end / S2 start")
    ax.axvline(hi, color="black", ls="--", lw=1.2, label="S2 end")
    ax.axhline(1695 / 30, color="darkviolet", ls=":", lw=1.2, label="1695 after x30")
    ax.set_title(f"run{rid} id={pid} over={row.frac_over_an * 100:.1f}% "
                 f"len(dy)={dy.size}", fontsize=9)
    ax.tick_params(labelsize=8)
    ax.set_xlabel("t from alignment ref [us]", fontsize=9)
    ax.set_ylabel("ADC", fontsize=9)
    ax.grid(True, alpha=0.2)
    ax.legend(fontsize=7, loc="upper right")

fig.suptitle("muon 7/7 peaks with S2 over-threshold fraction > 80%: "
             "dynode_sum vs anode_sum (n=10 shown)", fontsize=15)
fig.tight_layout(rect=(0, 0, 1, 0.97))
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=130)
plt.close(fig)
print("saved", NAME)
