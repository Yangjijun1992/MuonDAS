#!/usr/bin/env python
"""Plot 3 anode_sum/dynode_sum waveforms per run for the 163 widest lowright
high-energy events (width_ns>2000 & width_90area>300)."""
import sys, os
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np, pandas as pd
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end, find_sum_pulse_bounds
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db
from muon_analysis.plotting.waveforms import plot_peak_sum_waveform

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
base = "/mnt/data/tmp/muon_analysis/co60_590/peak_level/"
wide = pd.read_csv(base + "co60_590_lowright_h40000_wide.csv")
outdir = base + "wide163_waveforms"
os.makedirs(outdir, exist_ok=True)

for rid in sorted(wide.run_id.unique()):
    rid5 = f"{int(rid):05d}"
    sub = wide[wide.run_id == rid].sort_values("width_ns", ascending=False).head(3)
    if sub.empty:
        continue
    ids = set(sub.peaks_id.astype(int).tolist())
    ri = get_runinfo(rid5, cfg["data_source"]["data_root"], runtype="run7_Xe")
    rd = read_data(ri, "waveform_analysis_records")
    peaks = {p.peaks_id: p for p in cluster_peaks(match_events(rd, cfg), rd, cfg)
             if p.peaks_id in ids}
    compute_peak_start_end(list(peaks.values()), rd, cfg)
    g = build_gain_db(cfg, run_id=rid5)
    for pid in ids:
        pk = peaks.get(pid)
        if pk is None:
            print(f"{rid5} peak {pid} not found", flush=True); continue
        pf = compute_peak_features(pk, rd, g, cfg)
        b = find_sum_pulse_bounds(pf.anode_sum, pf.dynode_sum, cfg)
        p = plot_peak_sum_waveform(pk, pf.anode_sum, pf.dynode_sum, outdir, rid5,
                                   dynode_invert=True, bounds=b)
        print(f"{rid5} peak {pid}: w_ns={pf.width_ns:.0f} w90={pf.width_90area:.0f} "
              f"h={pf.height:.0f} n_ch={pk.n_channels} -> {os.path.basename(p[0])}",
              flush=True)
print("DONE")
open(os.path.join(outdir, "done.flag"), "w").write("DONE")
