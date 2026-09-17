#!/usr/bin/env python
"""Illustrate the end_first issue with ONE waveform (run 595).

Two separate canvases:
  1. the whole peak sum waveform (with a_st / end_first / end_final markers);
  2. a zoom-in centred on the point where the signal decays to 1/3 of its peak
     height, spanning +/-5 us, with the y-axis limited to 1/10 of the peak.
This waveform is the reference case for validating the S1-end algorithm."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end, find_sum_pulse_bounds
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

PEAK_ID = 20791
RUN = "00595"
OUT = "/home/yjj/MuonDAS/docs/figures"

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
ri = get_runinfo(RUN, cfg["data_source"]["data_root"], runtype="run7_Xe")
rd = read_data(ri, "waveform_analysis_records")
peaks = list(cluster_peaks(match_events(rd, cfg), rd, cfg))
compute_peak_start_end(peaks, rd, cfg)
g = build_gain_db(cfg, run_id=RUN)

pk = next(p for p in peaks if p.peaks_id == PEAK_ID)
pf = compute_peak_features(pk, rd, g, cfg)
s = np.asarray(pf.anode_sum, dtype=float)
b = find_sum_pulse_bounds(s, pf.dynode_sum, cfg)
a_st = b["anode"][0] if "anode" in b else 0
interval = float(cfg["matching"]["sample_interval_ns"])
height = float(np.abs(s).max())
peak_idx = int(np.argmin(s))

after = np.nonzero(np.abs(s[peak_idx:]) <= height / 3.0)[0]
third_idx = peak_idx + int(after[0]) if len(after) else peak_idx
print(f"peak_id={PEAK_ID} len={len(s)} a_st={a_st} end_first={pf.end_first_sample} "
      f"end_final={pf.end_final_sample} height={height:.0f} peak_idx={peak_idx} "
      f"third_idx={third_idx} ({(third_idx-a_st)*interval/1000:.2f} us after a_st)")

t = (np.arange(len(s)) - a_st) * interval / 1000.0

fig, ax = plt.subplots(figsize=(15, 6))
ax.plot(t, s, "b-", lw=0.7, label="anode_sum")
for x, c, lb in [(a_st, "g", "a_st"), (pf.end_first_sample, "m", "end_first"),
                 (pf.end_final_sample, "k", "end_final")]:
    ax.axvline((x - a_st) * interval / 1000.0, color=c, ls="--", lw=1.6, label=lb)
ax.axvline((third_idx - a_st) * interval / 1000.0, color="orange", ls=":", lw=1.8,
           label="1/3 height decay")
ax.set_xlabel("time rel. to anode-sum start [us]", fontsize=14)
ax.set_ylabel("anode_sum [ADC]", fontsize=14)
ax.set_title(f"run {RUN} peak_id={PEAK_ID}: whole peak sum waveform "
             f"(S1w={pf.muon_s1_width_ns:.0f}ns S2w={pf.muon_s2_width_ns:.0f}ns "
             f"width={pf.width:.0f})", fontsize=12)
ax.legend(fontsize=11, loc="upper right")
ax.tick_params(labelsize=12)
fig.tight_layout()
p1 = f"{OUT}/issue_end_first_full.png"
fig.savefig(p1, dpi=150)
plt.close(fig)
print("saved:", p1)

t0 = (third_idx - a_st) * interval / 1000.0
fig, ax = plt.subplots(figsize=(15, 7))
ax.plot(t, s, "b-", lw=0.9, label="anode_sum")
for x, c, lb in [(a_st, "g", "a_st"), (pf.end_first_sample, "m", "end_first"),
                 (pf.end_final_sample, "k", "end_final")]:
    ax.axvline((x - a_st) * interval / 1000.0, color=c, ls="--", lw=1.6, label=lb)
ax.axvline(t0, color="orange", ls=":", lw=2.0, label="1/3 height decay")
ax.axhline(0, color="gray", ls="-", lw=0.8)
ax.set_xlim(t0 - 5.0, t0 + 5.0)
ax.set_ylim(-height / 10.0, height / 10.0)
ax.set_xlabel("time rel. to anode-sum start [us]", fontsize=14)
ax.set_ylabel("anode_sum [ADC]", fontsize=14)
ax.set_title(f"run {RUN} peak_id={PEAK_ID}: zoom +/-5us around 1/3-height decay "
             f"(y = +/-1/10 peak = {height/10:.0f} ADC)", fontsize=12)
ax.legend(fontsize=11, loc="upper right")
ax.tick_params(labelsize=12)
fig.tight_layout()
p2 = f"{OUT}/issue_end_first_zoom.png"
fig.savefig(p2, dpi=150)
plt.close(fig)
print("saved:", p2)

post = s[a_st + 200: a_st + 500]
print(f"post-prompt baseline (a_st+200..500): median={np.median(post):.1f} "
      f"min={np.min(post):.1f} max={np.max(post):.1f} "
      f"tol={cfg['pulse_finder']['end_baseline_tol']}")
