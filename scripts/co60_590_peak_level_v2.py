#!/usr/bin/env python
"""Re-process Co60 590+ (18 runs) with the NEW clustering (pulse-start
reference + 320 ns window) and peak-level parameters (S1/S2 widths, two end
points).  Resumable: per-run CSV + skip completed; merges at the end."""
import sys, os, glob
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np, pandas as pd
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16   # Co60
runs = [f"{int(r):05d}" for r in pd.read_csv(
    "/home/yjj/MuonDAS/docs/run7_xe_calibration_run_590_plus.csv")["run_id"]]
OUT = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2"
os.makedirs(OUT, exist_ok=True)

PARAMS = ['height','width','rise_time','width_ns','width_90area','width_50area',
          'width_20_50area','n_samples_gt1000adc','area_ano','area_dyn',
          'anode_area_pe','dynode_area_pe','anode_sum_area','dynode_sum_area',
          'end_first_sample','end_final_sample','muon_s1_width_ns',
          'muon_s2_width_ns','wave_len_samples']
for rid in runs:
    done = os.path.join(OUT, f"run_{rid}.csv")
    if os.path.exists(done):
        continue
    t0 = os.times()[4]
    try:
        ri = get_runinfo(rid, cfg["data_source"]["data_root"], runtype="run7_Xe")
        rd = read_data(ri, "waveform_analysis_records")
        matched = match_events(rd, cfg)
        peaks = list(cluster_peaks(matched, rd, cfg))
        compute_peak_start_end(peaks, rd, cfg)
        g = build_gain_db(cfg, run_id=rid)
        rows = []
        for pk in peaks:
            pf = compute_peak_features(pk, rd, g, cfg)
            d = {k: getattr(pf, k) for k in PARAMS}
            d.update({'run_id': rid, 'peaks_id': pk.peaks_id,
                      'n_ch': pk.n_channels, 'n_anode': len(pk.anode_records),
                      'n_dynode': len(pk.dynode_records),
                      'signal_type': pf.signal_type})
            rows.append(d)
        pd.DataFrame(rows).to_csv(done, index=False)
        msg = f"[{rid}] pairs={len(matched)} peaks={len(peaks)} ({os.times()[4]-t0:.0f}s)"
        print(msg, flush=True)
        open(os.path.join(OUT, "progress.log"), "a").write(msg + "\n")
    except Exception as e:
        msg = f"[{rid}] ERROR {e}"
        print(msg, flush=True)
        open(os.path.join(OUT, "progress.log"), "a").write(msg + "\n")

files = sorted(glob.glob(os.path.join(OUT, "run_*.csv")))
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()
df.to_csv(os.path.join(OUT, "co60_590_peak_level_v2.csv"), index=False)
print(f"\nDONE total peaks={len(df)}")
print(df.signal_type.value_counts().to_dict() if len(df) else {})
open(os.path.join(OUT, "done.flag"), "w").write("DONE")
