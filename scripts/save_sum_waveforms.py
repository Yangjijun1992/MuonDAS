#!/usr/bin/env python
"""Persist the per-peak anode_sum / dynode_sum waveforms of the Co60 590+ runs.

One npz per run under <OUT>/sum_waveforms/run_<rid>.npz (see
muon_analysis.sum_store for the layout).  Resumable: existing files are skipped.
"""
import sys
import os
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import pandas as pd
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.features import compute_peak_summed_waveforms
from muon_analysis.sum_store import save_sum_npz

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
runs = [f"{int(r):05d}" for r in pd.read_csv(
    "/home/yjj/MuonDAS/docs/run7_xe_calibration_run_590_plus.csv")["run_id"]]
OUT = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/sum_waveforms"
os.makedirs(OUT, exist_ok=True)

for rid in runs:
    path = os.path.join(OUT, f"run_{rid}.npz")
    if os.path.exists(path):
        print(f"[{rid}] exists, skip", flush=True)
        continue
    ri = get_runinfo(rid, cfg["data_source"]["data_root"], runtype="run7_Xe")
    rd = read_data(ri, "waveform_analysis_records")
    peaks = list(cluster_peaks(match_events(rd, cfg), rd, cfg))
    compute_peak_start_end(peaks, rd, cfg)
    ids, a_sums, d_sums, ref = [], [], [], 50
    for pk in peaks:
        a, d, ref, _ = compute_peak_summed_waveforms(pk, rd, cfg)
        ids.append(pk.peaks_id)
        a_sums.append(a)
        d_sums.append(d)
    save_sum_npz(path, ids, a_sums, d_sums, sum_ref=ref)
    n_a = sum(len(x) for x in a_sums if x is not None)
    n_d = sum(len(x) for x in d_sums if x is not None)
    print(f"[{rid}] peaks={len(ids)} anode_samples={n_a} dynode_samples={n_d} "
          f"-> {os.path.basename(path)}", flush=True)

print("DONE")
