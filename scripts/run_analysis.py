#!/usr/bin/env python3
"""Command-line entry point for Muon dynode/anode fast analysis.

Examples:
  python scripts/run_analysis.py 00179
  python scripts/run_analysis.py 00179 00180 --config config/analysis.yaml
  python scripts/run_analysis.py '00*' --out-dir output/foo --parallel
  python scripts/run_analysis.py --show-cache
  python scripts/run_analysis.py --clear-cache
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from muon_analysis import cache
from muon_analysis.config import build_config
from muon_analysis.io.run_index import resolve_run_ids
from muon_analysis.pipeline import analyze_runs


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Muon dynode/anode fast analysis")
    p.add_argument("run_ids", nargs="*", help="run ids or glob patterns")
    p.add_argument("--run-list", type=str, default=None,
                   help="file with run ids/patterns, one per line")
    p.add_argument("--config", type=str, default=None,
                   help="path to YAML config file")
    p.add_argument("--data-root", type=str, default="",
                   help="overwrite data_root for runinfo discovery")
    p.add_argument("--data-format", type=str, default="",
                   help="overwrite data_format (waveform_analysis_records|npy|hdf5)")
    p.add_argument("--runtype", type=str, default="",
                   help="explicit runtype to scope runinfo search "
                        "(e.g. run6_Xe; empty => auto-discover)")
    p.add_argument("--runtype-candidates", type=str, default="",
                   help="comma-separated restricted runtype list to probe")
    p.add_argument("--relaxed-filters", action="store_true",
                   help="disable length/area/height filter thresholds (for toy data)")
    p.add_argument("--gain-backend", type=str, default="",
                   choices=["", "pmtdata", "sqlite", "csv"],
                   help="override gain_db backend")
    p.add_argument("--gain-path", type=str, default="",
                   help="path for sqlite/csv gain backend (with --gain-backend)")
    p.add_argument("--pattern", type=str, default="",
                   help="path to PMT pattern file for COG/track reconstruction")
    p.add_argument("--out-dir", type=str, default="output",
                   help="output directory")
    p.add_argument("--no-save-waveforms", action="store_true",
                   help="disable .npy waveform clip output")
    p.add_argument("--save-waveforms", dest="save_waveforms",
                   action="store_true", help="enable .npy waveform output")
    p.add_argument("--no-save-plots", action="store_true",
                   help="disable plot generation")
    p.add_argument("--plot-ids", type=str, default=None,
                   help="comma-separated anode record_ids to plot individually")
    p.add_argument("--plot-peaks", type=str, default=None,
                   help="comma-separated peak/event indices to plot (verification)")
    p.add_argument("--no-progress", action="store_true",
                   help="disable tqdm progress bars")
    p.add_argument("--no-cache", action="store_true",
                   help="disable use of the /mnt/data/tmp/muon_analysis cache")
    p.add_argument("--show-cache", action="store_true",
                   help="list cache entries and exit")
    p.add_argument("--clear-cache", action="store_true",
                   help="clear the cache directory and exit")
    p.add_argument("--parallel", action="store_true",
                   help="process runs in parallel (not yet paralleled per-run)")
    p.add_argument("--debug", action="store_true", help="verbose output")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    config = build_config(args.config)
    overrides: dict = {}

    if args.show_cache:
        cache.show_cache(config)
        return 0
    if args.clear_cache:
        n = cache.clear_cache(config)
        print(f"Cleared {n} cache file(s) in {cache.cache_dir_for(config)}")
        return 0

    if not args.run_ids and not args.run_list:
        print("Error: at least one run_id (or --run-list) is required.", file=sys.stderr)
        build_parser().print_help(sys.stderr)
        return 2

    run_ids = resolve_run_ids(args.run_ids, args.run_list)

    if args.no_save_waveforms:
        overrides["output"] = overrides.get("output", {})
        overrides["output"]["save_waveforms"] = False
    if args.save_waveforms:
        overrides["output"] = overrides.get("output", {})
        overrides["output"]["save_waveforms"] = True
    if args.no_save_plots:
        overrides["output"] = overrides.get("output", {})
        overrides["output"]["save_plots"] = False
    if args.data_format:
        overrides["data_source"] = overrides.get("data_source", {})
        overrides["data_source"]["data_format"] = args.data_format
    if args.runtype:
        overrides["runinfo"] = overrides.get("runinfo", {})
        overrides["runinfo"]["runtype"] = args.runtype
    if args.runtype_candidates:
        rt_list = [t.strip() for t in args.runtype_candidates.split(",")
                   if t.strip()]
        overrides["runinfo"] = overrides.get("runinfo", {})
        overrides["runinfo"]["runtype_candidates"] = rt_list
    if args.relaxed_filters:
        overrides["filtering"] = {
            "min_event_length": 0,
            "min_seg_area_pe": None,
            "signal_positive_polarity": {"asym_min": 0.0},
            "signal_negative_polarity": {"asym_min": 0.0},
        }
    if args.gain_backend:
        overrides["gain_db"] = overrides.get("gain_db", {})
        overrides["gain_db"]["backend"] = args.gain_backend
    if args.gain_path:
        overrides["gain_db"] = overrides.get("gain_db", {})
        if args.gain_backend == "csv":
            overrides["gain_db"]["csv_path"] = args.gain_path
        else:
            overrides["gain_db"]["sqlite_path"] = args.gain_path
    if args.pattern:
        overrides["cog"] = overrides.get("cog", {})
        overrides["cog"]["pattern_path"] = args.pattern

    plot_ids = None
    if args.plot_ids:
        plot_ids = [int(x) for x in args.plot_ids.split(",") if x.strip()]

    plot_peaks = None
    if args.plot_peaks:
        plot_peaks = [int(x) for x in args.plot_peaks.split(",") if x.strip()]

    if args.no_progress:
        overrides["progress"] = False

    rc = analyze_runs(
        run_ids=run_ids,
        output_dir=args.out_dir,
        data_root=args.data_root or config["data_source"].get("data_root", ""),
        config_path=args.config,
        use_cache=not args.no_cache,
        save_plots=not args.no_save_plots,
        plot_ids=plot_ids,
        plot_peaks=plot_peaks,
        parallel=args.parallel,
        config_overrides=overrides,
    )
    return rc


if __name__ == "__main__":
    sys.exit(main())
