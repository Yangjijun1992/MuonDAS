#!/usr/bin/env python
"""30 example muon peaks whose anode AND dynode channels are ALL triggered (n=7/7).

Reads the persisted sum-waveform npz (muon_analysis.sum_store) + the peak level
CSV.  Each panel: anode_sum (solid) and the flipped dynode_sum (dashed), with the
muon S1 start / S1 end / S1 peak drawn as lw=0.5 vertical dashed lines.
x window: -0.2 us .. +1.8 us (2 us) from the alignment reference (record start)."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.sum_store import load_sum_npz

N_EX = 30
X_START, X_WIN = -0.2, 2.0
TMP = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_muon_7ch_s1_examples.png"

ratio = pd.read_csv(f"{TMP}/muon_an_dy_channel_ratio.csv")
d = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
m = ratio[(ratio.n_an_pulse == 7) & (ratio.n_dy_pulse == 7)][["run_id", "peaks_id"]]
sel = d.merge(m, on=["run_id", "peaks_id"]).sort_values("muon_s1_area_an")
print(f"7ch/7ch muon peaks = {len(sel)}")

# 30 examples spread over the muon_s1_area_an quantiles
picks = sel.iloc[[int(round(i * (len(sel) - 1) / (N_EX - 1))) for i in range(N_EX)]]
print(f"picked = {len(picks)}")
print(picks[["run_id", "peaks_id", "muon_s1_area_an", "muon_s1_area_dy",
             "muon_s1_height_an"]].to_string(index=False))

ncol = 5
nrow = (len(picks) + ncol - 1) // ncol
fig, axes = plt.subplots(nrow, ncol, figsize=(4.8 * ncol, 3.4 * nrow))
axes = np.atleast_1d(axes).ravel()
cache = {}

for ax, (_, row) in zip(axes, picks.iterrows()):
    rid = int(row.run_id)
    if rid not in cache:
        cache[rid] = load_sum_npz(f"{TMP}/sum_waveforms/run_{rid:05d}.npz")
    store = cache[rid]
    pid = int(row.peaks_id)
    a = np.asarray(store["anode_sums"].get(pid, np.zeros(0)), dtype=float)
    dy = np.asarray(store["dynode_sums"].get(pid, np.zeros(0)), dtype=float)
    if a.size == 0:
        ax.axis("off")
        continue
    ref = int(store["sum_ref"])
    lo, mid = int(row.muon_s1_start_sample), int(row.muon_s1_end_sample)
    s1_peak = int(np.argmin(a))
    t = (np.arange(len(a)) - ref) * 4 / 1000.0
    ax.plot(t, a, "royalblue", lw=0.9, label="anode_sum")
    if dy.size:
        ax.plot((np.arange(len(dy)) - ref) * 4 / 1000.0, -dy, "crimson", ls="--",
                lw=0.9, alpha=0.85, label="dynode_sum (flipped)")
    for x, c, lb, ls in [(lo, "green", "S1 start", "--"),
                         (mid, "orange", "S1 end", "-."),
                         (s1_peak, "purple", "S1 peak", ":")]:
        ax.axvline((x - ref) * 4 / 1000.0, color=c, ls=ls, lw=0.5, label=lb)
    ax.axhline(0, color="black", ls="--", alpha=0.3, lw=0.5)
    ax.set_xlim(X_START, X_START + X_WIN)
    ax.set_title(f"run{rid} id={pid} n7/7 "
                 f"as_an={row.muon_s1_area_an:.0f} as_dy={row.muon_s1_area_dy:.0f} "
                 f"h_an={row.muon_s1_height_an:.0f} h_dy={row.muon_s1_height_dy:.0f}",
                 fontsize=7)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("t from alignment ref [us]", fontsize=8)
    ax.set_ylabel("ADC", fontsize=8)
    ax.legend(fontsize=6, loc="upper right")

fig.suptitle("muon peaks with ALL 7/7 channels triggered (anode & dynode), "
             f"x = {X_START:+.1f} .. {X_START + X_WIN:+.1f} us (n={len(picks)} shown)",
             fontsize=14)
fig.tight_layout(rect=(0, 0, 1, 0.98))
for out in (f"{TMP}/{NAME}", f"{DOCS}/{NAME}"):
    fig.savefig(out, dpi=130)
plt.close(fig)
print("saved:", NAME)
