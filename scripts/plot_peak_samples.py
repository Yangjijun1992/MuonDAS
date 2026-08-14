#!/usr/bin/env python3
"""Plot verification waveforms (with peak start/end marked) for a random
sample of multi-channel peaks, for visual inspection.

Usage (conda activate py12):
  python scripts/plot_peak_samples.py 00183 --n 10 --seed 0 \
      --out-dir /mnt/data/tmp/muon_analysis/validate_00183/random_peaks \
      --plot-len 150
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np

from muon_analysis.config import build_config
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.plotting.waveforms import plot_peak_verification
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id", help="run id (e.g. 00183)")
    p.add_argument("--n", type=int, default=10, help="number of random peaks")
    p.add_argument("--seed", type=int, default=0, help="random seed")
    p.add_argument("--min-channels", type=int, default=7,
                   help="sample from peaks with n_channels >= this")
    p.add_argument("--plot-len", type=int, default=150, help="samples per plot")
    p.add_argument("--out-dir", default="",
                   help="output directory (default: /mnt/data/tmp/muon_analysis/"
                        "validate_<run>/random_peaks)")
    p.add_argument("--data-root", default="", help="overwrite data_root")
    args = p.parse_args(argv)

    config = build_config()
    if args.data_root:
        config["data_source"]["data_root"] = args.data_root

    run_id = str(args.run_id)
    out_dir = Path(args.out_dir) if args.out_dir else Path(
        f"/mnt/data/tmp/muon_analysis/validate_{run_id}/random_peaks")
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    print(f"[{run_id}] reading ...")
    ri = get_runinfo(run_id, config["data_source"]["data_root"],
                     runtype=config["runinfo"].get("runtype") or None,
                     runtype_candidates=config["runinfo"].get(
                         "runtype_candidates") or None)
    run_data = read_data(ri, config["data_source"].get(
        "data_format", "waveform_analysis_records"),
        data_dir=config["data_source"].get("data_dir"))
    print(f"  read {time.time()-t0:.1f}s")

    t0 = time.time()
    peaks = cluster_peaks(match_events(run_data, config), run_data, config)
    print(f"  clustered {len(peaks)} peaks ({time.time()-t0:.1f}s)")

    cand = [pk for pk in peaks if pk.n_channels >= args.min_channels]
    print(f"  candidates (n_channels>={args.min_channels}): {len(cand)}")

    compute_peak_start_end(cand, run_data, config)

    rng = np.random.default_rng(args.seed)
    idx = rng.choice(len(cand), size=min(args.n, len(cand)), replace=False)
    for i in sorted(idx):
        pk = cand[i]
        w = pk.end_time_ns - pk.start_time_ns
        print(f"  peak {pk.peaks_id}: {pk.n_channels} ch  "
              f"start={pk.start_time_ns:.0f} end={pk.end_time_ns:.0f}ns "
              f"宽={w:.0f}ns")
        saved = plot_peak_verification(
            pk, run_data, out_dir, run_id, plot_len=args.plot_len,
            lp_cutoff_hz=config.get("plotting", {}).get("dynode_lp_cutoff_hz"),
            fs=float(config.get("plotting", {}).get("fs", 250e6)))
        for s in saved:
            print(f"    saved: {s}")
    print(f"\nplots in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
