#!/usr/bin/env python
"""Per-side triggered-channel counts for muon peaks: n_an_pulse / n_dy_pulse.

For every muon peak, count the anode and dynode records whose pulse finder
resolved a pulse (``pulse_start_sample is not None``) and save the ratio.
Resumable per run; merged into muon_an_dy_channel_ratio.csv at the end."""
import sys
import os
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
runs = [f"{int(r):05d}" for r in pd.read_csv(
    "/home/yjj/MuonDAS/docs/run7_xe_calibration_run_590_plus.csv")["run_id"]]
D = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
OUT = f"{D}/an_dy_ratio"
os.makedirs(OUT, exist_ok=True)

for rid in runs:
    path = os.path.join(OUT, f"run_{rid}.csv")
    if os.path.exists(path):
        print(f"[{rid}] exists, skip", flush=True)
        continue
    csv = pd.read_csv(f"{D}/run_{rid}.csv")
    mu = set(csv[csv.signal_type == "muon"].peaks_id.astype(int))
    if not mu:
        pd.DataFrame().to_csv(path, index=False)
        continue
    ri = get_runinfo(rid, cfg["data_source"]["data_root"], runtype="run7_Xe")
    rd = read_data(ri, "waveform_analysis_records")
    peaks = list(cluster_peaks(match_events(rd, cfg), rd, cfg))
    compute_peak_start_end(peaks, rd, cfg)
    rows = []
    for pk in peaks:
        if pk.peaks_id not in mu:
            continue
        na = sum(1 for r in pk.anode_records if r.pulse_start_sample is not None)
        nd = sum(1 for r in pk.dynode_records if r.pulse_start_sample is not None)
        rows.append({"run_id": int(rid), "peaks_id": pk.peaks_id,
                     "n_anode_rec": len(pk.anode_records),
                     "n_dynode_rec": len(pk.dynode_records),
                     "n_an_pulse": na, "n_dy_pulse": nd})
    pd.DataFrame(rows).to_csv(path, index=False)
    print(f"[{rid}] muon peaks={len(rows)}", flush=True)

files = sorted(f"{OUT}/{f}" for f in os.listdir(OUT) if f.endswith(".csv"))
d = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
d["ratio"] = d.n_an_pulse / d.n_dy_pulse.replace(0, np.nan)
d.to_csv(f"{D}/muon_an_dy_channel_ratio.csv", index=False)
print(f"\nDONE rows={len(d)}  ratio median={d.ratio.median():.3f}  "
      f"non-1={((d.ratio != 1) & d.ratio.notna()).mean()*100:.1f}%")
