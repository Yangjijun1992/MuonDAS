#!/usr/bin/env python
"""Batch process run7_Xe TPC runs: match -> cluster (NO muon filtering),
collect matched dt distribution. Outputs under tpc_run7_xe/ (separate naming)."""
import sys, os, time, json
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd

from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks

cfg = build_config()
runs = [f"{r:05d}" for r in pd.read_csv(
    "/home/yjj/MuonDAS/docs/run7_xe_tpc_run.csv")["run_id"]]
OUT = "/mnt/data/tmp/muon_analysis/tpc_run7_xe"
os.makedirs(OUT, exist_ok=True)

LOG = os.path.join(OUT, "progress.log")
rows = []
all_dt = []
for i, rid in enumerate(runs, 1):
    t0 = time.time()
    try:
        ri = get_runinfo(rid, cfg["data_source"]["data_root"], runtype="run7_Xe")
        rd = read_data(ri, "waveform_analysis_records")
        matched = match_events(rd, cfg)
        peaks = list(cluster_peaks(matched, rd, cfg))
        dt = matched["dt"].to_numpy()
        all_dt.append(dt)
        np.save(os.path.join(OUT, f"{rid}_matched_dt.npy"), dt)
        rows.append({"run_id": rid, "n_anode": len(rd.anode_records),
                     "n_dynode": len(rd.dynode_records),
                     "n_matched": len(dt), "n_peaks": len(peaks),
                     "dt_median": float(np.median(dt)), "dt_mean": float(np.mean(dt)),
                     "dt_p16": float(np.percentile(dt, 16)),
                     "dt_p84": float(np.percentile(dt, 84))})
        msg = f"[{rid}] {i}/{len(runs)} n_matched={len(dt)} n_peaks={len(peaks)} dt_med={np.median(dt):.1f} ({time.time()-t0:.0f}s)"
        print(msg, flush=True)
        with open(LOG, "a") as f:
            f.write(msg + "\n")
    except Exception as e:
        msg = f"[{rid}] ERROR {e}"
        print(msg, flush=True)
        with open(LOG, "a") as f:
            f.write(msg + "\n")

df = pd.DataFrame(rows)
df.to_csv(os.path.join(OUT, "tpc_run7_xe_matched_summary.csv"), index=False)
dt_all = np.concatenate(all_dt) if all_dt else np.array([])
np.save(os.path.join(OUT, "all_matched_dt.npy"), dt_all)

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(12, 7))
ax.hist(dt_all, bins=np.arange(-5, 205, 2), histtype="step", color="navy", lw=1.5)
ax.axvline(np.median(dt_all), color="r", ls="--", label=f"median={np.median(dt_all):.1f}")
ax.set_xlabel("matched dt (dynode-anode, after shift) [ns]", fontsize=15)
ax.set_ylabel("counts", fontsize=15)
ax.set_title(f"run7_Xe TPC Run 匹配 dt 分布 (n={len(dt_all)}, {len(runs)} runs)", fontsize=15)
ax.legend(fontsize=13)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "tpc_run7_xe_matched_dt_histogram.png"), dpi=140)
print(f"\nDONE. total matched={len(dt_all)}  median={np.median(dt_all):.1f}  "
      f"p16={np.percentile(dt_all,16):.1f}  p84={np.percentile(dt_all,84):.1f}")
print("summary:", os.path.join(OUT, "tpc_run7_xe_matched_summary.csv"))
print("hist:", os.path.join(OUT, "tpc_run7_xe_matched_dt_histogram.png"))
