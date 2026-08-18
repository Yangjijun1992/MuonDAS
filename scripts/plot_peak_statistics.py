#!/usr/bin/env python3
"""Plot peak-level parameter statistics (1D histograms + key 2D histograms)
from the exported muon-candidate CSV, for signal selection.

Usage (conda activate py12):
  python scripts/plot_peak_statistics.py 00183
  # outputs to /mnt/data/tmp/muon_analysis/muon_candidates_00183_n7/statistics/
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from muon_analysis.plotting.distributions import (
    plot_peak_parameter_histograms,
    plot_rise_time_histograms,
)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id", help="run id (e.g. 00183)")
    p.add_argument("--csv", default="", help="candidate CSV path (default: "
                   "/mnt/data/tmp/muon_analysis/muon_candidates_<run>_n7/"
                   "<run>_muon_candidates.csv)")
    p.add_argument("--npz", default="", help="waveforms npz path (default: "
                   "same dir as CSV /<run>_waveforms.npz)")
    p.add_argument("--out-dir", default="", help="output directory (default: "
                   "same dir as CSV /statistics)")
    args = p.parse_args(argv)

    run_id = str(args.run_id)
    csv_path = Path(args.csv) if args.csv else Path(
        f"/mnt/data/tmp/muon_analysis/muon_candidates_{run_id}_n7/"
        f"{run_id}_muon_candidates.csv")
    npz_path = Path(args.npz) if args.npz else csv_path.parent / f"{run_id}_waveforms.npz"
    out_dir = Path(args.out_dir) if args.out_dir else csv_path.parent / "statistics"
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(csv_path)
    print(f"candidates: {len(df)}  (CSV: {csv_path})")
    saved = plot_peak_parameter_histograms(df, out_dir, run_id)
    if npz_path.exists():
        saved += plot_rise_time_histograms(npz_path, out_dir, run_id)
    for s in saved:
        print(f"  saved: {s}")
    print(f"\n{len(saved)} plots in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
