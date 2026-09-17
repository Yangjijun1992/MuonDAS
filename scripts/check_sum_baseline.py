#!/usr/bin/env python
"""Why does end_first (a_ed) land at the waveform end for long peaks?
Check the anode_sum post-prompt baseline offset vs end_baseline_tol (20 ADC)."""
import sys
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end, find_sum_pulse_bounds
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
ri = get_runinfo("00595", cfg["data_source"]["data_root"], runtype="run7_Xe")
rd = read_data(ri, "waveform_analysis_records")
peaks = list(cluster_peaks(match_events(rd, cfg), rd, cfg))
compute_peak_start_end(peaks, rd, cfg)
g = build_gain_db(cfg, run_id="00595")

want = pd.read_csv("/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/run_00595.csv")
want = want[(want.wave_len_samples > 5000) & (want.n_ch == 7)]
ids = set(int(i) for i in want.peaks_id)

tol = float(cfg["pulse_finder"]["end_baseline_tol"])
print(f"end_baseline_tol = {tol}")
print(f"{'id':>7} {'len':>5} {'a_st':>5} {'end1':>5} {'pre_bl':>8} "
      f"{'post_bl':>8} {'post_min':>9} {'post_max':>9} {'n|bl|>tol':>9}")
for pk in peaks:
    if pk.peaks_id not in ids:
        continue
    pf = compute_peak_features(pk, rd, g, cfg)
    s = pf.anode_sum
    b = find_sum_pulse_bounds(s, pf.dynode_sum, cfg)
    a_st = b["anode"][0] if "anode" in b else 0
    pre = float(np.mean(s[:max(1, a_st)]))
    post = s[a_st + 200: a_st + 500]
    n_off = int(np.count_nonzero(np.abs(post) > tol))
    print(f"{pk.peaks_id:>7} {len(s):>5} {a_st:>5} {pf.end_first_sample:>5} "
          f"{pre:>8.1f} {float(np.median(post)):>8.1f} {float(np.min(post)):>9.1f} "
          f"{float(np.max(post)):>9.1f} {n_off:>4}/{len(post)}")
