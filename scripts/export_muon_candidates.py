#!/usr/bin/env python3
"""Export multi-channel (n_channels >= min_channels) peaks for detailed analysis.

Extracts peak-level data + raw waveforms for the muon-candidate subset
(e.g. all 7-channel hits) so the user can run further offline analysis and
determine muon selection criteria.

Outputs (default under /mnt/data/tmp/muon_analysis/muon_candidates_<run>_n<k>/):
  <run>_muon_candidates.csv   one row per peak (features, PE, COG, record ids)
  <run>_waveforms.npz         per-record waveforms (object array, unpadded)
  manifest.json               dataset description + config used

Usage (conda activate py12):
  python scripts/export_muon_candidates.py 00183 --min-channels 7 \
      --out-dir /mnt/data/tmp/muon_analysis/muon_candidates_00183_n7
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from muon_analysis.config import build_config
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.features import compute_peak_features
from muon_analysis.filtering import SignalAccessor
from muon_analysis.gain import build_gain_db
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.cog import cog_reconstruct_peak, load_pmt_layout
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("run_id", help="run id (e.g. 00183)")
    p.add_argument("--min-channels", type=int, default=7,
                   help="keep peaks with n_channels >= this value")
    p.add_argument("--out-dir", default="",
                   help="output directory (default: /mnt/data/tmp/muon_analysis/"
                        "muon_candidates_<run>_n<k>)")
    p.add_argument("--data-root", default="", help="overwrite data_root")
    args = p.parse_args(argv)

    config = build_config()
    if args.data_root:
        config["data_source"]["data_root"] = args.data_root

    run_id = str(args.run_id)
    out_dir = Path(args.out_dir) if args.out_dir else Path(
        f"/mnt/data/tmp/muon_analysis/muon_candidates_{run_id}_n{args.min_channels}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- read / match / cluster ---
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
    match_df = match_events(run_data, config)
    print(f"  matched {len(match_df)} pairs ({time.time()-t0:.1f}s)")

    t0 = time.time()
    peaks = cluster_peaks(match_df, run_data, config)
    print(f"  clustered {len(peaks)} peaks ({time.time()-t0:.1f}s)")
    compute_peak_start_end(peaks, run_data, config)

    sel = [pk for pk in peaks if pk.n_channels >= args.min_channels]
    print(f"  selected {len(sel)} peaks with n_channels >= {args.min_channels}")
    if not sel:
        print("  nothing to export")
        return 1

    # --- features + COG ---
    gain_db = build_gain_db(config, run_id=ri.run_id)
    feats = {pk.peaks_id: compute_peak_features(pk, run_data, gain_db, config)
             for pk in tqdm(sel, desc="features")}
    layout = load_pmt_layout(config, ri)
    positions = layout.pmt_positions_by_id if layout else None

    # --- per-record waveforms ---
    accessor = SignalAccessor.from_run_data(run_data)
    rows = []
    for pk in tqdm(sel, desc="waveforms"):
        for rec in pk.anode_records + pk.dynode_records:
            wf = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                            dtype=np.int16)
            rows.append((pk.peaks_id, int(rec.is_dynode), rec.channel,
                         rec.record_id, rec.time_ns, wf))
    wf_peaks = np.array([r[0] for r in rows], dtype=np.int64)
    wf_board = np.array([r[1] for r in rows], dtype=np.int8)
    wf_ch = np.array([r[2] for r in rows], dtype=np.int16)
    wf_rec = np.array([r[3] for r in rows], dtype=np.int64)
    wf_time = np.array([r[4] for r in rows], dtype=np.float64)
    wf_waves = np.empty(len(rows), dtype=object)
    for i, r in enumerate(rows):
        wf_waves[i] = r[5]

    # --- candidate CSV (peak level, with per-channel PE) ---
    records = []
    for pk in sel:
        f = feats[pk.peaks_id]
        row = f.as_dict()
        row["start_time_ns"] = pk.start_time_ns
        row["end_time_ns"] = pk.end_time_ns
        cog = cog_reconstruct_peak(f, ri, positions, config) if positions else None
        row["cog_x"], row["cog_y"] = (float(cog[0]), float(cog[1])) if cog else (np.nan, np.nan)
        for rec in pk.anode_records:
            row[f"pe_anode_ch{rec.channel}"] = f.anode_pe.get(rec.record_id, np.nan)
        for rec in pk.dynode_records:
            row[f"pe_dynode_ch{rec.channel}"] = f.dynode_pe.get(rec.record_id, np.nan)
        records.append(row)
    csv_path = out_dir / f"{run_id}_muon_candidates.csv"
    pd.DataFrame(records).to_csv(csv_path, index=False)

    npz_path = out_dir / f"{run_id}_waveforms.npz"
    np.savez(
        npz_path,
        peaks_id=wf_peaks, board=wf_board, channel=wf_ch, record_id=wf_rec,
        time_ns=wf_time, waveforms=wf_waves,
    )

    manifest = {
        "run_id": run_id,
        "runtype": ri.runtype,
        "min_channels": args.min_channels,
        "total_matched_pairs": int(len(match_df)),
        "total_peaks": int(len(peaks)),
        "selected_peaks": int(len(sel)),
        "total_waveforms": int(len(rows)),
        "layout_source": layout.source if layout else None,
        "files": {
            "csv": csv_path.name,
            "npz": npz_path.name,
        },
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(f"\ncandidate CSV : {csv_path}")
    print(f"waveforms npz : {npz_path}")
    print(f"manifest      : {out_dir / 'manifest.json'}")
    print(f"selected peaks: {len(sel)}, waveforms: {len(rows)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
