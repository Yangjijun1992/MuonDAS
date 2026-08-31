#!/usr/bin/env python3
"""Peak-level anode/dynode charge-ratio statistics across all runs.

For each run: read -> match -> cluster -> keep n_channels>=7 peaks ->
pulse start/end -> peak features; collect (run_id, peaks_id,
anode_area_pe, dynode_area_pe, ratio).  Saves per-run CSVs, a merged CSV
and a ratio histogram.

Outputs under /mnt/data/tmp/muon_analysis/ratio_stats/
Usage (conda activate py12):
  python scripts/stat_anode_dynode_ratio.py
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

OUT_ROOT = Path("/mnt/data/tmp/muon_analysis/ratio_stats")
MIN_CHANNELS = 7


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
        a = pf.anode_area_pe
        d = pf.dynode_area_pe
        rows.append({
            "run_id": str(run_id),
            "peaks_id": pk.peaks_id,
            "anode_area_pe": a,
            "dynode_area_pe": d,
            "ratio_anode_over_dynode": a / d if d else float("nan"),
            "height": pf.height,
            "width_ns": pf.width_ns,
        })
    print(f"[{run_id}] {len(rows)} rows ({time.time()-t0:.0f}s)", flush=True)
    df = pd.DataFrame(rows)
    p = out_root / f"{run_id}_ratio.csv"
    df.to_csv(p, index=False)
    return df


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--runs", default="", help="comma-separated run list "
                   "(default: all from docs/tpc_runs.csv)")
    p.add_argument("--csv", default="docs/tpc_runs.csv")
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
        out_csv = out_root / f"{rid}_ratio.csv"
        if out_csv.exists():
            print(f"[{rid}] cached, skip", flush=True)
            dfs.append(pd.read_csv(out_csv))
            continue
        df = process_run(rid, config, out_root)
        if df is not None:
            dfs.append(df)

    if not dfs:
        print("no data")
        return 1
    merged = pd.concat(dfs, ignore_index=True)
    merged_path = out_root / "merged_ratio.csv"
    merged.to_csv(merged_path, index=False)
    print(f"\nmerged: {len(merged)} peaks from {merged['run_id'].nunique()} runs")

    r = merged["ratio_anode_over_dynode"].dropna()
    print(f"ratio stats: n={len(r)} median={r.median():.3f} "
          f"mean={r.mean():.3f} q25={r.quantile(.25):.3f} "
          f"q75={r.quantile(.75):.3f}")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.hist(r, bins=80, histtype="step")
    ax.axvline(r.median(), color="r", ls="--", lw=1.2,
               label=f"median {r.median():.2f}")
    ax.set_xlabel("peak-level anode_area_pe / dynode_area_pe")
    ax.set_ylabel("Counts")
    ax.set_title(f"Anode/Dynode charge ratio (n_ch>={MIN_CHANNELS} peaks, "
                 f"{len(merged)} events, {merged['run_id'].nunique()} runs)")
    ax.legend()
    fig.tight_layout()
    hist = out_root / "ratio_histogram.png"
    fig.savefig(hist, dpi=120)
    plt.close(fig)
    print(f"histogram: {hist}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
