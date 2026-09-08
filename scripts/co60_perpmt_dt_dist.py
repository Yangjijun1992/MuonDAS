#!/usr/bin/env python3
"""Per-PMT anode/dynode raw delta-time distribution (run7_Xe calibration runs).

For each run: read raw records -> per-channel match anode & dynode
(merge_asof, backward, per channel) -> compute the RAW delta time
``dt = t_dyn - t_ano`` directly from the raw ``time`` field (NO global
``dynode_shift_ns`` / per-channel delay applied), then collect dt per channel.

One PMT == one channel (run7_Xe anode/dynode share channels 9..15).

Prints a per-channel dt statistics table per run and a combined table, and
saves per-channel dt histograms (step + filled overlay), per-channel .npy and
a combined summary CSV.

Outputs under /mnt/data/tmp/muon_analysis/co60_perpmt_dt/
Usage (conda activate py12):
  python scripts/co60_perpmt_dt_dist.py
  python scripts/co60_perpmt_dt_dist.py --csv docs/run7_xe_calibration_run.csv --n-runs 4
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import get_matched_indices_by_channel, shift_time_records

DEFAULT_CSV = "docs/run7_xe_calibration_run.csv"
DEFAULT_OUT_ROOT = Path("/mnt/data/tmp/muon_analysis/co60_perpmt_dt")

# dt window used to collect raw matched pairs (captures the physical peak
# 0-32 ns plus the early shoulder; far-spurious pairs are excluded).
DT_MIN, DT_MAX = 0.0, 80.0
# histogram range for the per-PMT figures.
HIST_MIN, HIST_MAX, HIST_STEP = 0.0, 80.0, 2.0


def per_channel_raw_dt(run_id: str, config) -> pd.DataFrame:
    """Load one run and return a DataFrame of raw matched dt per channel.

    Returns columns ``[run_id, channel, dt]`` (dt in ns, dynode - anode).
    """
    ri = get_runinfo(run_id, config["data_source"]["data_root"], runtype="run7_Xe")
    run_data = read_data(ri, "waveform_analysis_records")

    # RAW delta time: apply a ZERO dynode shift so ``dt`` is the raw DAQ
    # dynode-anode difference, un-calibrated.
    dyn_raw = shift_time_records(np.copy(run_data.dynode_records), 0.0)
    matched = get_matched_indices_by_channel(
        run_data.anode_records, dyn_raw, min_diff=DT_MIN, max_diff=DT_MAX
    )
    matched["channel"] = matched["channel"].astype(int)
    out = matched[["channel", "dt"]].copy()
    out["dt"] = out["dt"].astype(float)
    out["run_id"] = str(run_id)
    return out[["run_id", "channel", "dt"]]


def stats_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per-channel dt statistics summary."""
    rows = []
    for ch in sorted(df["channel"].unique()):
        d = df.loc[df["channel"] == ch, "dt"].to_numpy(dtype=float)
        rows.append({
            "channel": int(ch),
            "n": len(d),
            "mean": float(np.mean(d)),
            "median": float(np.median(d)),
            "p16": float(np.percentile(d, 16)),
            "p84": float(np.percentile(d, 84)),
            "min": float(d.min()),
            "max": float(d.max()),
            "std": float(np.std(d)),
        })
    return pd.DataFrame(rows).sort_values("channel").reset_index(drop=True)


def print_table(title: str, tab: pd.DataFrame) -> None:
    print(f"\n=== {title} ===")
    print(tab.to_string(index=False, float_format=lambda v: f"{v:8.1f}"))


def plot_per_channel(df: pd.DataFrame, out_dir: Path, label: str) -> None:
    """Save a step + filled-overlay per-channel dt histogram."""
    bins = np.arange(HIST_MIN, HIST_MAX + HIST_STEP, HIST_STEP)
    channels = sorted(df["channel"].unique())

    # stacked step per channel
    fig, ax = plt.subplots(figsize=(12, 7))
    for ch in channels:
        d = df.loc[df["channel"] == ch, "dt"].to_numpy(dtype=float)
        ax.hist(d, bins=bins, histtype="step", lw=1.5,
                label=f"ch{ch} (n={len(d)})")
    ax.set_xlabel("raw dynode - anode dt [ns]", fontsize=14)
    ax.set_ylabel("counts", fontsize=14)
    ax.set_title(f"Per-PMT raw anode/dynode dt {label} (n={len(df)})", fontsize=14)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3, ls=":")
    fig.tight_layout()
    step = out_dir / f"perpmt_dt_step_{label}.png"
    fig.savefig(step, dpi=140)
    plt.close(fig)

    # filled overlay
    fig, ax = plt.subplots(figsize=(12, 7))
    cols = plt.cm.tab10(np.linspace(0, 1, len(channels)))
    for ch, c in zip(channels, cols):
        d = df.loc[df["channel"] == ch, "dt"].to_numpy(dtype=float)
        ax.hist(d, bins=bins, histtype="stepfilled", alpha=0.45, color=c,
                label=f"ch{ch} (n={len(d)})")
    ax.set_xlabel("raw dynode - anode dt [ns]", fontsize=14)
    ax.set_ylabel("counts", fontsize=14)
    ax.set_title(f"Per-PMT raw anode/dynode dt {label} (n={len(df)})", fontsize=14)
    ax.legend(fontsize=9)
    ax.grid(alpha=0.3, ls=":")
    fig.tight_layout()
    overlay = out_dir / f"perpmt_dt_overlay_{label}.png"
    fig.savefig(overlay, dpi=140)
    plt.close(fig)

    # per-channel individual figure with median marker
    fig, axes = plt.subplots(1, len(channels), figsize=(3.2 * len(channels), 5.5))
    if len(channels) == 1:
        axes = [axes]
    for ax, ch in zip(axes, channels):
        d = df.loc[df["channel"] == ch, "dt"].to_numpy(dtype=float)
        ax.hist(d, bins=bins, histtype="step", color="navy", lw=1.5)
        med = float(np.median(d))
        ax.axvline(med, color="r", ls="--", lw=1.4,
                   label=f"med={med:.1f}ns (n={len(d)})")
        ax.set_title(f"ch{ch}", fontsize=12)
        ax.set_xlabel("dt [ns]", fontsize=10)
        ax.grid(alpha=0.3, ls=":")
        ax.legend(fontsize=8)
    axes[0].set_ylabel("counts", fontsize=11)
    fig.suptitle(f"Per-PMT raw anode/dynode dt {label}", fontsize=14)
    fig.tight_layout()
    grid = out_dir / f"perpmt_dt_grid_{label}.png"
    fig.savefig(grid, dpi=140)
    plt.close(fig)

    return step, overlay, grid


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", default=DEFAULT_CSV,
                   help="run table (must have a 'run_id' column)")
    p.add_argument("--n-runs", type=int, default=4,
                   help="number of runs to take from the top of the CSV")
    p.add_argument("--out-root", default=str(DEFAULT_OUT_ROOT))
    p.add_argument("--data-root", default="", help="overwrite data_source.data_root")
    args = p.parse_args(argv)

    run_ids = pd.read_csv(args.csv)["run_id"].iloc[: args.n_runs]
    run_ids = [str(r).zfill(5) for r in run_ids]
    print(f"runs to process (raw dt, no shift): {run_ids}")

    config = build_config()
    if args.data_root:
        config["data_source"]["data_root"] = args.data_root

    out_root = Path(args.out_root)
    out_root.mkdir(parents=True, exist_ok=True)

    frames: list[pd.DataFrame] = []
    per_run: dict[str, pd.DataFrame] = {}
    for rid in run_ids:
        t0 = time.time()
        try:
            df = per_channel_raw_dt(rid, config)
        except Exception as e:  # noqa: BLE001  keep processing remaining runs
            print(f"[{rid}] ERROR: {e}", flush=True)
            continue
        frames.append(df)
        per_run[rid] = df
        tab = stats_table(df)
        print_table(f"{rid} raw dt (nyanode-dynode) ", tab)
        print(f"[{rid}] matched={len(df)} ({time.time() - t0:.1f}s)", flush=True)
        # per-run figure
        plot_per_channel(df, out_root, str(rid))

    if not frames:
        print("no data collected")
        return 1

    combined = pd.concat(frames, ignore_index=True)
    combined.to_csv(out_root / "perpmt_raw_dt.csv", index=False)

    tab_all = stats_table(combined)
    print_table("COMBINED raw dt (all runs)", tab_all)

    # per-channel npy dumps (dt values per channel, all runs merged)
    for ch in sorted(combined["channel"].unique()):
        arr = combined.loc[combined["channel"] == ch, "dt"].to_numpy(dtype=float)
        np.save(out_root / f"channel_{ch}_dt.npy", arr)

    tab_all.to_csv(out_root / "perpmt_raw_dt_stats.csv", index=False)

    plots = plot_per_channel(combined, out_root, "combined")
    print(f"\nDONE n={len(combined)} over {len(per_run)} runs "
          f"channels={sorted(combined['channel'].unique())}")
    print("summary CSV:", out_root / "perpmt_raw_dt_stats.csv")
    for fname in plots:
        print("figure:", fname)
    return 0


if __name__ == "__main__":
    sys.exit(main())
