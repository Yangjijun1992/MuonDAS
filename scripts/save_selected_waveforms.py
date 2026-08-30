#!/usr/bin/env python3
"""Save peak-level anode/dynode verification waveforms for all selected muon
candidates (from muon_select_batch/merged_selected.csv).

For each (run_id, peaks_id): read the run once, locate the peak, compute
pulse start/end, and save the anode overlay, dynode overlay and compare
figures (plot_peak_verification, 3 PNGs per event).

Output: <out-root>/waveforms/<run>_peak<peaks_id>_verify_*.png
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
from muon_analysis.plotting.waveforms import plot_peak_verification
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data

DEFAULT_MERGED = ("/mnt/data/tmp/muon_analysis/muon_select_batch/"
                  "merged_selected.csv")
OUT_ROOT = Path("/mnt/data/tmp/muon_analysis/muon_select_batch")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default=DEFAULT_MERGED)
    p.add_argument("--out-root", default=str(OUT_ROOT))
    p.add_argument("--data-root", default="", help="overwrite data_root")
    args = p.parse_args(argv)

    merged = pd.read_csv(args.csv)
    events = list(zip(merged["run_id"].astype(str), merged["peaks_id"].astype(int)))
    print(f"events to plot: {len(events)}")

    config = build_config()
    if args.data_root:
        config["data_source"]["data_root"] = args.data_root
    out_dir = Path(args.out_root) / "waveforms"
    out_dir.mkdir(parents=True, exist_ok=True)

    run_cache = {}
    for run_id, peaks_id in events:
        if run_id not in run_cache:
            t0 = time.time()
            ri = get_runinfo(run_id, config["data_source"]["data_root"],
                             runtype=config["runinfo"].get("runtype") or None,
                             runtype_candidates=config["runinfo"].get(
                                 "runtype_candidates") or None)
            run_data = read_data(ri, config["data_source"].get(
                "data_format", "waveform_analysis_records"),
                data_dir=config["data_source"].get("data_dir"))
            peaks = {pp.peaks_id: pp for pp in cluster_peaks(
                match_events(run_data, config), run_data, config)}
            print(f"[{run_id}] read+cluster {time.time()-t0:.0f}s", flush=True)
            run_cache[run_id] = (ri, run_data, peaks)
        ri, run_data, peaks = run_cache[run_id]

        pk = peaks.get(int(peaks_id))
        if pk is None:
            print(f"  [{run_id}] peak {peaks_id} not found, skip")
            continue
        compute_peak_start_end([pk], run_data, config)
        saved = plot_peak_verification(pk, run_data, out_dir, run_id,
                                       adaptive=True)
        print(f"  [{run_id}] peak {peaks_id}: {len(saved)} plots")

    print(f"\nall in: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
