#!/usr/bin/env python
"""Batch Co60 (590+) runs -> peak level using current pipeline.
dynode_shift=-16 (Co60), baseline=0 pulse finder, rise_time>=0 clamp."""
import sys, os
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
OUT = "/mnt/data/tmp/muon_analysis/co60_590/peak_level"
os.makedirs(OUT, exist_ok=True)
LOG = os.path.join(OUT, "progress.log")

PARAMS = ['height','width','rise_time','width_ns','width_90area','width_50area',
          'width_20_50area','area_ano','area_dyn','anode_area_pe','dynode_area_pe',
          'anode_sum_area','dynode_sum_area']
rows = []
for rid in runs:
    t0 = os.times()[4]
    try:
        ri = get_runinfo(rid, cfg["data_source"]["data_root"], runtype="run7_Xe")
        rd = read_data(ri, "waveform_analysis_records")
        matched = match_events(rd, cfg)
        peaks = list(cluster_peaks(matched, rd, cfg))
        compute_peak_start_end(peaks, rd, cfg)
        g = build_gain_db(cfg, run_id=rid)
        for pk in peaks:
            pf = compute_peak_features(pk, rd, g, cfg)
            d = {k: getattr(pf, k) for k in PARAMS}
            d.update({'run_id': rid, 'peaks_id': pk.peaks_id,
                      'n_ch': pk.n_channels, 'n_anode': len(pk.anode_records),
                      'n_dynode': len(pk.dynode_records),
                      'anode_area_pe_recon': pf.anode_area_pe_recon,
                      'n_anode_saturated': pf.n_anode_saturated})
            rows.append(d)
        msg = f"[{rid}] pairs={len(matched)} peaks={len(peaks)} ({os.times()[4]-t0:.0f}s)"
        print(msg, flush=True)
        with open(LOG, "a") as f:
            f.write(msg + "\n")
    except Exception as e:
        msg = f"[{rid}] ERROR {e}"
        print(msg, flush=True)
        with open(LOG, "a") as f:
            f.write(msg + "\n")

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT, "co60_590_peak_level.csv"), index=False)
n_neg = (df.rise_time < 0).sum() if len(df) else 0
print(f"\nDONE total peaks={len(df)} neg_rise_time={n_neg}")
open(os.path.join(OUT, "done.flag"), "w").write("DONE")
print(os.path.join(OUT, "co60_590_peak_level.csv"))
