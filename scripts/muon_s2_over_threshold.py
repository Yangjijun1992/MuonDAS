#!/usr/bin/env python
"""S2 waveform amplitude distributions and over-threshold statistics for muon peaks.

For every muon peak whose anode and dynode channels are ALL triggered
(n_an_pulse == 7 and n_dy_pulse == 7) take the anode_sum / dynode_sum S2 segment
[muon_s1_end_sample, muon_s2_end_sample), histogram the sample amplitudes in ADC
(raw and x30 scaled) and count the samples above 1695 after the x30 scaling.
The stored sum waveforms are baseline subtracted."""
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
BINS = np.logspace(0, 7, 160)

ratio = pd.read_csv(f"{TMP}/muon_an_dy_channel_ratio.csv")
df = pd.read_csv(f"{TMP}/co60_590_peak_level_v2.csv")
m = df.merge(ratio[(ratio.n_an_pulse == 7) & (ratio.n_dy_pulse == 7)][["run_id", "peaks_id"]],
             on=["run_id", "peaks_id"])
print(f"7ch/7ch muon peaks = {len(m)}")

ha_raw = np.zeros(BINS.size - 1)
ha_sc = np.zeros(BINS.size - 1)
hd_raw = np.zeros(BINS.size - 1)
hd_sc = np.zeros(BINS.size - 1)
rows = []
cache = {}
for _, row in m.iterrows():
    rid = int(row.run_id)
    if rid not in cache:
        cache[rid] = load_sum_npz(f"{TMP}/sum_waveforms/run_{rid:05d}.npz")
    store = cache[rid]
    pid = int(row.peaks_id)
    ref = int(store["sum_ref"])
    lo = max(int(row.muon_s1_end_sample) - ref, 0)
    hi = max(int(row.muon_s2_end_sample) - ref, 0)
    a = -np.asarray(store["anode_sums"].get(pid, np.zeros(0)), dtype=float)[lo:hi]
    dy = np.asarray(store["dynode_sums"].get(pid, np.zeros(0)), dtype=float)[lo:hi]
    if a.size == 0:
        continue
    ha_raw += np.histogram(a, bins=BINS)[0]
    ha_sc += np.histogram(a * SCALE, bins=BINS)[0]
    if dy.size:
        hd_raw += np.histogram(dy, bins=BINS)[0]
        hd_sc += np.histogram(dy * SCALE, bins=BINS)[0]
    rows.append({"run_id": rid, "peaks_id": pid,
                 "n_points_an": a.size, "n_over_an": int((a * SCALE > THRESH).sum()),
                 "n_points_dy": dy.size, "n_over_dy": int((dy * SCALE > THRESH).sum())})
d = pd.DataFrame(rows)
d["frac_over_an"] = d.n_over_an / d.n_points_an
d.to_csv(f"{TMP}/muon_7ch_s2_over1695.csv", index=False)

tot_pts = int(d.n_points_an.sum())
tot_over = int(d.n_over_an.sum())
print(f"waveforms={len(d)}  anode points={tot_pts}  over {THRESH:g} (x{SCALE:g}) = {tot_over} "
      f"({tot_over / tot_pts * 100:.3f}%)")
print(f"  dynode points={int(d.n_points_dy.sum())}  over={int(d.n_over_dy.sum())} "
      f"({d.n_over_dy.sum() / max(d.n_points_dy.sum(), 1) * 100:.3f}%)")
print(f"anode n_points: min={d.n_points_an.min()} median={d.n_points_an.median():.0f} max={d.n_points_an.max()}")
print(f"anode n_over  : min={d.n_over_an.min()} median={d.n_over_an.median():.0f} max={d.n_over_an.max()}")
print(f"anode frac    : median={d.frac_over_an.median():.4f} max={d.frac_over_an.max():.4f}")
print(f"dynode n_points: min={d.n_points_dy.min()} median={d.n_points_dy.median():.0f} max={d.n_points_dy.max()}")

c = BINS[:-1] + np.diff(BINS) / 2
fig, axes = plt.subplots(1, 3, figsize=(31, 9))

for ax, hraw, hsc, tag in [(axes[0], ha_raw, ha_sc, "anode_sum"),
                           (axes[2], hd_raw, hd_sc, "dynode_sum")]:
    ax.step(c, hraw, where="mid", color="royalblue", lw=2.2, label="original [ADC]")
    ax.step(c, hsc, where="mid", color="darkorange", lw=2.2, label=f"x{SCALE:g} scale [ADC]")
    ax.axvline(THRESH, color="darkviolet", ls="--", lw=2.8, label=f"threshold {THRESH:g}")
    ax.set_xscale("log")
    ax.set_xlabel(f"S2 amplitude ({tag}) [ADC]", fontsize=22, fontweight="bold")
    ax.legend(framealpha=0.9, fontsize=16)

axes[1].hist(d.frac_over_an * 100, bins=120, color="seagreen", alpha=0.8)
axes[1].set_xlabel(f"fraction over {THRESH:g} [%]", fontsize=22, fontweight="bold")
for ax in axes:
    ax.set_ylabel("Counts", fontsize=22, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.25)
    ax.tick_params(labelsize=15)
    ax.set_yscale("log")
fig.suptitle(f"muon 7/7 peaks: S2 (anode_sum / dynode_sum) amplitude and over-threshold "
             f"statistics (n={len(d)}, baseline subtracted)\n"
             f"anode: {tot_pts} points, {tot_over} over threshold after x{SCALE:g} "
             f"({tot_over / tot_pts * 100:.2f}%)",
             fontsize=21, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.92))
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=150)
plt.close(fig)
print("saved", NAME)
