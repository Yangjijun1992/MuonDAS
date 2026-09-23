#!/usr/bin/env python
"""Co60 590+ peak level v3: v2 + peak time stamp + long-S2 <-> S1 pairing.

Runs the full per-run pipeline (read -> match -> cluster -> features/signal_id),
then -- as part of the same flow, right after the peak classification -- pairs
every long S2 (width > muon_pair.s2_width_min_ns) with the largest unpaired S1
inside the preceding muon_pair.window_ns window and flags both members of a
successful pair as ``is_paired_event`` (paired events are NOT muon events).
Resumable per run."""
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
from muon_analysis.physical_pair import mark_paired_events

cfg = build_config()
cfg["matching"]["dynode_shift_ns"] = -16
pc = cfg.get("muon_pair", {}) or {}
WINDOW_NS = float(pc.get("window_ns", 25000.0))
S2_WIDTH_MIN = float(pc.get("s2_width_min_ns", 10000.0))
runs = [f"{int(r):05d}" for r in pd.read_csv(
    "/home/yjj/MuonDAS/docs/run7_xe_calibration_run_590_plus.csv")["run_id"]]
OUT = "/mnt/data/tmp/muon_analysis/co60_590/peak_level_v3"
os.makedirs(OUT, exist_ok=True)

PARAMS = ['height','width','rise_time','width_90area','width_50area',
          'width_20_50area','n_samples_gt1000adc','area_ano','area_dyn',
          'anode_area_pe','dynode_area_pe','anode_sum_area','dynode_sum_area',
          'end_first_sample','end_final_sample',
          'muon_s1_start_sample','muon_s1_end_sample','muon_s2_end_sample',
          'muon_s1_width_ns','muon_s2_width_ns','muon_s1_height_an','muon_s2_height_an',
          'muon_s1_height_dy','muon_s2_height_dy',
          'muon_s1_area_an','muon_s1_area_dy','muon_s2_area_an','muon_s2_area_dy',
          'wave_len_samples']
print(f"window={WINDOW_NS:g} ns  s2_width_min={S2_WIDTH_MIN:g} ns", flush=True)

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
                      'peak_time_ns': float(pk.start_time_ns),
                      'n_ch': pk.n_channels, 'n_anode': len(pk.anode_records),
                      'n_dynode': len(pk.dynode_records),
                      'signal_type': pf.signal_type})
            rows.append(d)
        df = pd.DataFrame(rows)
        df, res = mark_paired_events(df, window_ns=WINDOW_NS,
                                     s2_width_min_ns=S2_WIDTH_MIN)
        df.to_csv(done, index=False)
        res["pairs"].to_csv(os.path.join(OUT, f"run_{rid}_pairs.csv"), index=False)
        n_pairs = len(res["pairs"])
        msg = (f"[{rid}] peaks={len(df)} longS2={res['n_long_s2']} pairs={n_pairs} "
               f"({os.times()[4]-t0:.0f}s)")
        print(msg, flush=True)
        open(os.path.join(OUT, "progress.log"), "a").write(msg + "\n")
    except Exception as e:
        msg = f"[{rid}] ERROR {e}"
        print(msg, flush=True)
        open(os.path.join(OUT, "progress.log"), "a").write(msg + "\n")

files = sorted(glob.glob(os.path.join(OUT, "run_0*.csv")))
files = [f for f in files if not f.endswith("_pairs.csv")]
df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True) if files else pd.DataFrame()
df.to_csv(os.path.join(OUT, "co60_590_peak_level_v3.csv"), index=False)
pfiles = sorted(glob.glob(os.path.join(OUT, "run_*_pairs.csv")))
pairs = pd.concat([pd.read_csv(f) for f in pfiles], ignore_index=True) if pfiles else pd.DataFrame()
pairs.to_csv(os.path.join(OUT, "muon_long_s2_s1_pairs.csv"), index=False)
print(f"\nDONE peaks={len(df)}  pairs={len(pairs)}  "
      f"is_paired_event={int(df.is_paired_event.sum()) if len(df) else 0}")
print(df.signal_type.value_counts().to_dict() if len(df) else {})
open(os.path.join(OUT, "done.flag"), "w").write("DONE")
