#!/usr/bin/env python3
"""Validate the full analysis flow on a real run, stage by stage.

Stages:
  1. read        waveform-level records (anode + dynode, split by board)
  2. match       waveform-level anode/dynode time matching (shift + merge_asof)
  3. cluster     peak-level clustering (100 ns window) -> peak summary CSV
  4. features    per-peak features (dynode LP + x110) + COG reconstruction
  5. verify      verification plots for N typical peaks:
                 - anode/dynode overlay (叠加)
                 - per-channel anode + dynode pairs (各 PMT 通道波形)

Usage:
  python scripts/validate_peaks.py 00183 --out-dir output/validate_00183 \
      --num-peaks 2 --plot-len 1500
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
from tqdm.auto import tqdm

from muon_analysis.config import build_config
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data


def _stage(name, elapsed):
    print(f"  [{name}] {elapsed:.1f}s")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id", help="run id (e.g. 00183)")
    p.add_argument("--out-dir", default="output/validate", help="output directory")
    p.add_argument("--num-peaks", type=int, default=2, help="typical peaks to plot")
    p.add_argument("--plot-len", type=int, default=1500,
                   help="waveform samples per plot window")
    p.add_argument("--data-root", default="", help="overwrite data_root")
    p.add_argument("--runtype", default="", help="explicit runtype")
    args = p.parse_args(argv)

    config = build_config()
    if args.data_root:
        config["data_source"]["data_root"] = args.data_root
    if args.runtype:
        config["runinfo"]["runtype"] = args.runtype

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(args.run_id)
    stats: dict = {}

    # --- 1. read ---
    print(f"== [{run_id}] stage 1: read ==")
    t0 = time.time()
    ri = get_runinfo(run_id, config["data_source"]["data_root"],
                     runtype=config["runinfo"].get("runtype") or None,
                     runtype_candidates=config["runinfo"].get(
                         "runtype_candidates") or None)
    fmt = config["data_source"].get("data_format", "waveform_analysis_records")
    run_data = read_data(ri, fmt, data_dir=config["data_source"].get("data_dir"))
    n_ano, n_dyn = len(run_data.anode_records), len(run_data.dynode_records)
    stats["runtype"] = ri.runtype
    stats["n_anode_records"] = n_ano
    stats["n_dynode_records"] = n_dyn
    print(f"  runtype={ri.runtype} anode={n_ano} dynode={n_dyn} "
          f"records, raw_dir={ri.raw_dir}")
    _stage("read", time.time() - t0)

    # --- 2. match (waveform level) ---
    print(f"== [{run_id}] stage 2: match ==")
    t0 = time.time()
    match_df = match_events(run_data, config)
    stats["matched_pairs"] = int(len(match_df))
    dt = match_df["dt"].to_numpy()
    stats["dt_ns"] = {"min": float(dt.min()), "mean": float(dt.mean()),
                      "max": float(dt.max())}
    print(f"  matched pairs = {len(match_df)}  "
          f"dt ∈ [{dt.min():.1f}, {dt.max():.1f}] ns (mean {dt.mean():.2f})")
    _stage("match", time.time() - t0)

    # --- 3. cluster -> peaks ---
    print(f"== [{run_id}] stage 3: cluster ==")
    t0 = time.time()
    peaks = cluster_peaks(match_df, run_data, config)
    compute_peak_start_end(peaks, run_data, config)
    stats["n_peaks"] = len(peaks)
    n_ch = np.array([p.n_channels for p in peaks])
    stats["channels_per_peak"] = {
        "mean": float(n_ch.mean()), "min": int(n_ch.min()), "max": int(n_ch.max())}
    print(f"  peaks = {len(peaks)}  "
          f"channels/peak: min={n_ch.min()} mean={n_ch.mean():.2f} max={n_ch.max()}")
    _stage("cluster", time.time() - t0)

    # peak-level summary CSV (all peaks)
    import pandas as pd
    rows = [{
        "peaks_id": pk.peaks_id,
        "start_time_ns": pk.start_time_ns,
        "end_time_ns": pk.end_time_ns,
        "n_channels": pk.n_channels,
        "channels": " ".join(map(str, pk.channels)),
        "n_anode": pk.n_anode,
        "n_dynode": pk.n_dynode,
        "anode_record_ids": " ".join(str(r.record_id) for r in pk.anode_records),
        "dynode_record_ids": " ".join(str(r.record_id) for r in pk.dynode_records),
    } for pk in peaks]
    peak_csv = out_dir / f"{run_id}_peaks_summary.csv"
    pd.DataFrame(rows).to_csv(peak_csv, index=False)
    print(f"  peak summary CSV: {peak_csv}")
    stats["peak_summary_csv"] = str(peak_csv)

    # --- 4. features + COG ---
    print(f"== [{run_id}] stage 4: features + COG ==")
    t0 = time.time()
    gain_db = build_gain_db(config, run_id=ri.run_id)
    feats = {pk.peaks_id: compute_peak_features(pk, run_data, gain_db, config)
             for pk in tqdm(peaks, desc="features")}
    _stage("features", time.time() - t0)

    from muon_analysis.cog import cog_reconstruct_peak, load_pmt_layout
    layout = load_pmt_layout(config, ri)
    cog_map = {}
    if layout is not None:
        positions = layout.pmt_positions_by_id
        for pk in peaks:
            cog = cog_reconstruct_peak(feats[pk.peaks_id], ri, positions, config)
            if cog is not None:
                cog_map[pk.peaks_id] = cog
        stats["cog_filled"] = len(cog_map)
        print(f"  layout source={layout.source} ({len(layout.entries)} PMTs), "
              f"COG filled = {len(cog_map)}/{len(peaks)}")
    else:
        print("  no PMT layout (no pattern file / runinfo pos / fallback)")

    # --- 5. select typical peaks + verification plots ---
    print(f"== [{run_id}] stage 5: select {args.num_peaks} typical peaks + plots ==")
    from muon_analysis.plotting.waveforms import plot_peak_overlay, plot_peak_pairs

    plot_cfg = config.get("plotting", {})
    lp_cutoff = plot_cfg.get("dynode_lp_cutoff_hz")
    if lp_cutoff is not None:
        lp_cutoff = float(lp_cutoff)
    dynode_scale = float(plot_cfg.get("dynode_scale", 110))

    scored = sorted(peaks, key=lambda pk: (pk.n_channels,
                                           feats[pk.peaks_id].dynode_area_pe),
                    reverse=True)
    selected = scored[: args.num_peaks]
    sel_info = []
    for pk in selected:
        f = feats[pk.peaks_id]
        sel_info.append({
            "peaks_id": pk.peaks_id,
            "start_time_ns": pk.start_time_ns,
            "n_channels": pk.n_channels,
            "channels": list(pk.channels),
            "anode_record_ids": [r.record_id for r in pk.anode_records],
            "dynode_record_ids": [r.record_id for r in pk.dynode_records],
            "anode_area_pe": f.anode_area_pe,
            "dynode_area_pe": f.dynode_area_pe,
            "peak_height": f.peak_height,
            "cog": cog_map.get(pk.peaks_id),
        })
        print(f"  peak {pk.peaks_id}: {pk.n_channels} ch "
              f"t0={pk.start_time_ns}ns anode_PE={f.anode_area_pe:.1f} "
              f"dynode_PE={f.dynode_area_pe:.1f} cog={cog_map.get(pk.peaks_id)}")
        overlay = plot_peak_overlay(
            pk, run_data, out_dir, run_id, sample_interval_ns=4.0,
            dynode_scale=dynode_scale, lp_cutoff_hz=lp_cutoff,
            fs=float(plot_cfg.get("fs", 250e6)), plot_len=args.plot_len)
        pairs = plot_peak_pairs(
            pk, run_data, out_dir, run_id, sample_interval_ns=4.0,
            dynode_scale=dynode_scale, lp_cutoff_hz=lp_cutoff,
            fs=float(plot_cfg.get("fs", 250e6)), plot_len=args.plot_len)
        for p in overlay + pairs:
            print(f"  plot: {p}")
    stats["selected_peaks"] = sel_info
    _stage("plots", time.time() - t0)

    summary = out_dir / f"{run_id}_stage_summary.json"
    summary.write_text(json.dumps(stats, indent=2, default=str))
    print(f"\nstage summary: {summary}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
