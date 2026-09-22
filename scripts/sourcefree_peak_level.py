#!/usr/bin/env python
"""Batch Source-free TPC runs -> peak level (resumable, per-run CSV).
dynode_shift=-16 (raw dt center +16ns), baseline=0, sub-sample width interp."""
import sys, os, glob
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import pandas as pd
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
runs = [f"{int(r):05d}" for r in pd.read_csv(
    "/home/yjj/MuonDAS/docs/run7_xe_tpc_run_sourcefree.csv")["run_id"]]
OUT = "/mnt/data/tmp/muon_analysis/sourcefree/peak_level"
os.makedirs(OUT, exist_ok=True)

PARAMS = ['height','width','rise_time','width_90area','width_50area',
          'width_20_50area','area_ano','area_dyn','anode_area_pe','dynode_area_pe',
          'anode_sum_area','dynode_sum_area']
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
                      'anode_area_pe_recon': pf.anode_area_pe_recon,
                      'n_anode_saturated': pf.n_anode_saturated})
            rows.append(d)
        pd.DataFrame(rows).to_csv(done, index=False)
        msg = f"[{rid}] peaks={len(peaks)} ({os.times()[4]-t0:.0f}s)"
        print(msg, flush=True)
        with open(os.path.join(OUT, "progress.log"), "a") as f:
            f.write(msg + "\n")
    except Exception as e:
        msg = f"[{rid}] ERROR {e}"
        print(msg, flush=True)
        with open(os.path.join(OUT, "progress.log"), "a") as f:
            f.write(msg + "\n")

files = sorted(glob.glob(os.path.join(OUT, "run_*.csv")))
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()
df.to_csv(os.path.join(OUT, "sourcefree_peak_level.csv"), index=False)
n_neg = (df.rise_time < 0).sum() if len(df) else 0
print(f"\nDONE total peaks={len(df)} neg_rise={n_neg}")
open(os.path.join(OUT, "done.flag"), "w").write("DONE")
print(os.path.join(OUT, "sourcefree_peak_level.csv"))
