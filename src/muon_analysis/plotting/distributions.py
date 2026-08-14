"""Statistical distribution plots for feature validation.

Aligned with the reference notebook ``plot_correlation`` (anode vs dynode
area, per-channel scatter) and 2D histograms (segment area vs length).
Outputs are saved as .png.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pandas as pd


def plot_correlation(
    anode: pd.DataFrame,
    dynode: pd.DataFrame,
    output_dir: str | Path,
    run_id: str,
) -> Path:
    """Anode Area[PE] vs Dynode Area[PE] scatter, coloured per channel."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(output_dir) / f"correlation_run_{run_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(9, 8))
    has_channel = "channel" in anode.columns and "channel" in dynode.columns
    if has_channel:
        ch_list = sorted(set(anode["channel"]).union(set(dynode["channel"])))
        colors = plt.cm.tab10(np.linspace(0, 1, len(ch_list)))
        markers = ["o", "s", "^", "v", "D", "*", "p", "h", "x", "+"]
        for i, ch in enumerate(ch_list):
            a_mask = anode["channel"] == ch
            plt.scatter(dynode["dynode_area_pe"][a_mask],
                        anode["anode_area_pe"][a_mask],
                        s=15, alpha=0.5, color=colors[i % len(colors)],
                        marker=markers[i % len(markers)], label=f"Channel {ch}",
                        edgecolors="none")
        plt.legend(bbox_to_anchor=(1.05, 1), loc="upper left", markerscale=2)
    else:
        plt.scatter(dynode["dynode_area_pe"], anode["anode_area_pe"],
                    s=15, alpha=0.5, edgecolors="none")

    plt.xlabel("Dynode Area [PE]")
    plt.ylabel("Anode Area [PE]")
    plt.title("Correlation: Anode Area vs Dynode Area")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return path


def plot_2d_hist(
    x: np.ndarray,
    y: np.ndarray,
    output_dir: str | Path,
    run_id: str,
    xlabel: str,
    ylabel: str,
    bins: int = 100,
    name: str = "2dhist",
) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    path = Path(output_dir) / f"{name}_run_{run_id}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(9, 7))
    counts, xe, ye, im = plt.hist2d(x, y, bins=bins, cmap="viridis", cmin=1)
    plt.colorbar(im, label="Counts")
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return path


def plot_distributions(
    df: pd.DataFrame,
    output_dir: str | Path,
    run_id: str,
) -> List[Path]:
    """Generate a set of feature distribution plots; returns saved paths."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: List[Path] = []

    hist_specs = [
        ("anode_area_pe", "Anode Area [PE]"),
        ("dynode_area_pe", "Dynode Area [PE]"),
        ("anode_seg_area_pe", "Anode Segment Area [PE]"),
        ("dt_ns", "Dynode-Anode dt [ns]"),
    ]
    for col, label in hist_specs:
        if col not in df.columns:
            continue
        p = out / f"hist_{col}_run_{run_id}.png"
        plt.figure()
        values = df[col].dropna()
        plt.hist(values, bins=100, histtype="step")
        plt.xlabel(label)
        plt.ylabel("Counts")
        plt.title(label)
        plt.tight_layout()
        plt.savefig(p, dpi=120)
        plt.close()
        saved.append(p)

    if "anode_area_pe" in df.columns and "dynode_area_pe" in df.columns:
        saved.append(plot_correlation(df, df, out, run_id))

    if {"anode_seg_area_pe", "event_length"}.issubset(df.columns):
        saved.append(plot_2d_hist(
            df["anode_seg_area_pe"].to_numpy(),
            df["event_length"].to_numpy(),
            out, run_id, "Anode Segment Area [PE]", "Event Length [samples]",
            name="segarea_len",
        ))

    return saved
