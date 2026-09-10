#!/usr/bin/env python
"""Recompute upright_n7 peaks with the new n_samples_gt1000adc parameter.
Processes only the runs involved; keeps peaks whose peaks_id is in the
upright_n7 set.  Resumable (per-run CSV)."""
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
cfg["matching"]["dynode_shift_ns"] = -16
base = "/mnt/data/tmp/muon_analysis/co60_590/peak_level/"
u7 = pd.read_csv(base + "co60_590_upright_n7_peaks.csv")
OUT = base + "upright_n7_recompute"
os.makedirs(OUT, exist_ok=True)
PARAMS = ['height','width','rise_time','width_ns','width_90area','width_50area',
          'width_20_50area','n_samples_gt1000adc','area_ano','area_dyn',
          'anode_area_pe','dynode_area_pe','anode_sum_area','dynode_sum_area']

for rid in sorted(u7.run_id.unique()):
    rid5 = f"{int(rid):05d}"
    done = os.path.join(OUT, f"run_{rid5}.csv")
    if os.path.exists(done):
        continue
    ids = set(u7[u7.run_id == rid].peaks_id.astype(int).tolist())
    t0 = os.times()[4]
    ri = get_runinfo(rid5, cfg["data_source"]["data_root"], runtype="run7_Xe")
    rd = read_data(ri, "waveform_analysis_records")
    peaks = [p for p in cluster_peaks(match_events(rd, cfg), rd, cfg)
             if p.peaks_id in ids]
    compute_peak_start_end(peaks, rd, cfg)
    g = build_gain_db(cfg, run_id=rid5)
    rows = []
    for pk in peaks:
        pf = compute_peak_features(pk, rd, g, cfg)
        d = {k: getattr(pf, k) for k in PARAMS}
        d.update({'run_id': rid5, 'peaks_id': pk.peaks_id, 'n_ch': pk.n_channels,
                  'signal_type': pf.signal_type})
        rows.append(d)
    pd.DataFrame(rows).to_csv(done, index=False)
    msg = f"[{rid5}] {len(rows)} peaks ({os.times()[4]-t0:.0f}s)"
    print(msg, flush=True)
    open(os.path.join(OUT, "progress.log"), "a").write(msg + "\n")

files = sorted(glob.glob(os.path.join(OUT, "run_*.csv")))
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()
df.to_csv(base + "co60_590_upright_n7_with_nsamp.csv", index=False)
print(f"\nDONE total={len(df)}")
open(os.path.join(OUT, "done.flag"), "w").write("DONE")
