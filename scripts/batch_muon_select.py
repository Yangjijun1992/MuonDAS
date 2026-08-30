#!/usr/bin/env python3
"""Batch muon-candidate selection across the tpc_runs.csv run list.

For each run: read -> match -> cluster -> keep n_channels>=7 peaks ->
pulse start/end -> peak features -> selection cuts
(peak_height>10000, anode_area_pe>5000 PE, peak_width_ns>5000) ->
store peak-level CSV.  A merged CSV plus parameter-distribution plots are
written at the end.

Outputs under /mnt/data/tmp/muon_analysis/muon_select_batch/:
  <run>_selected.csv        per-run selected peak-level data
  merged_selected.csv       all runs concatenated
  statistics/               parameter distributions of the selected peaks

Usage (conda activate py12):
  python scripts/batch_muon_select.py [--runs 00183,00184] [--out-root ...]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from muon_analysis.config import build_config
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data

OUT_ROOT = Path("/mnt/data/tmp/muon_analysis/muon_select_batch")

# Selection cuts
MIN_CHANNELS = 7
PEAK_H_MIN = 10000.0      # peak_height [ADC]
ANODE_PE_MIN = 5000.0     # anode_area_pe [PE]
WIDTH_NS_MIN = 5000.0     # peak_width_ns [ns]


def process_run(run_id: str, config, out_root: Path):
    t0 = time.time()
    print(f"[{run_id}] reading ...", flush=True)
    ri = get_runinfo(run_id, config["data_source"]["data_root"],
                     runtype=config["runinfo"].get("runtype") or None,
                     runtype_candidates=config["runinfo"].get(
                         "runtype_candidates") or None)
    run_data = read_data(ri, config["data_source"].get(
        "data_format", "waveform_analysis_records"),
        data_dir=config["data_source"].get("data_dir"))
    print(f"[{run_id}] read {time.time()-t0:.0f}s", flush=True)

    t0 = time.time()
    peaks = [p for p in cluster_peaks(match_events(run_data, config),
                                      run_data, config)
             if p.n_channels >= MIN_CHANNELS]
    print(f"[{run_id}] {len(peaks)} peaks n_ch>={MIN_CHANNELS} "
          f"({time.time()-t0:.0f}s)", flush=True)
    if not peaks:
        return None

    compute_peak_start_end(peaks, run_data, config)
    gain_db = build_gain_db(config, run_id=ri.run_id)

    rows = []
    for pk in peaks:
        pf = compute_peak_features(pk, run_data, gain_db, config)
        if not (pf.peak_height > PEAK_H_MIN
                and pf.anode_area_pe > ANODE_PE_MIN
                and pf.peak_width_ns > WIDTH_NS_MIN):
            continue
        row = pf.as_dict()
        row.update({
            "run_id": str(run_id),
            "start_time_ns": pk.start_time_ns,
            "end_time_ns": pk.end_time_ns,
            "gain_db_version": gain_db.version,
        })
        rows.append(row)
    print(f"[{run_id}] selected {len(rows)} ({time.time()-t0:.0f}s)", flush=True)
    if not rows:
        return None

    df = pd.DataFrame(rows)
    p = out_root / f"{run_id}_selected.csv"
    df.to_csv(p, index=False)
    return df


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", default="", help="comma-separated run list "
                   "(default: all from docs/tpc_runs.csv)")
    p.add_argument("--csv", default="docs/tpc_runs.csv", help="run list CSV")
    p.add_argument("--out-root", default=str(OUT_ROOT))
    p.add_argument("--data-root", default="", help="overwrite data_root")
    args = p.parse_args(argv)

    if args.runs:
        run_ids = [r.strip() for r in args.runs.split(",") if r.strip()]
    else:
        df0 = pd.read_csv(args.csv)
        run_ids = [str(r) for r in df0["run_id"]]
    print(f"runs to process: {len(run_ids)}")

    config = build_config()
    if args.data_root:
        config["data_source"]["data_root"] = args.data_root
    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    dfs = []
    for rid in run_ids:
        out_csv = out_root / f"{rid}_selected.csv"
        if out_csv.exists():
            print(f"[{rid}] cached, skip", flush=True)
            dfs.append(pd.read_csv(out_csv))
            continue
        df = process_run(rid, config, out_root)
        if df is not None:
            dfs.append(df)

    if dfs:
        merged = pd.concat(dfs, ignore_index=True)
        merged_path = out_root / "merged_selected.csv"
        merged.to_csv(merged_path, index=False)
        print(f"\nmerged: {len(merged)} peaks -> {merged_path}")

        from muon_analysis.plotting.distributions import plot_peak_parameter_histograms
        stat_dir = out_root / "statistics"
        saved = plot_peak_parameter_histograms(merged, stat_dir, "batch")
        print(f"statistics plots: {len(saved)} -> {stat_dir}")
    else:
        print("no selected peaks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
