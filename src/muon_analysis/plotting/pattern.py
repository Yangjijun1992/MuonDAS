"""PMT pattern area-map plots: layout geometry + per-PMT charge + COG marker.

Ported from the reference ``xihu_fast_analysis/display.py`` conventions:
rotated PMT squares, inner/outer ring radii, LogNorm viridis charge
colouring and the charge-centre (CoQ/COG) marker.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

PMT_CAD_ROTATION_DEG = 30.0
PMT_SQUARE_SIDE_MM = 21.5
INNER_RING_RADIUS_MM = 39.0
OUTER_RING_RADIUS_MM = 62.0


def plot_pmt_area_map(
    layout,
    charge_per_pmt: Dict[str, float],
    output_dir: str | Path,
    run_id: str,
    index: Optional[int] = None,
    title: Optional[str] = None,
) -> Path:
    """Draw the PMT layout with per-PMT charge colouring and the COG marker.

    PMTs are drawn as rotated squares at their ``(x_mm, y_mm)`` positions,
    coloured by the charge weight (LogNorm viridis; zero-charge PMTs grey).
    The weighted charge centre is overlaid as a red ``x``.  Saved as
    ``pmt_area_run_<run_id>[__<index>].png`` (matplotlib Agg backend).

    Parameters
    ----------
    layout: :class:`~muon_analysis.cog.PmtLayout`
    charge_per_pmt: ``pmt_id -> charge weight`` (as in PeakFeatures).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.cm import ScalarMappable
    from matplotlib.colors import LogNorm, Normalize
    from matplotlib.patches import Rectangle

    entries = sorted(layout.entries, key=lambda e: e.pmt_no)
    by_id = layout.pmt_positions_by_id
    values = np.asarray(
        [float(charge_per_pmt.get(e.pmt_id, 0.0)) for e in entries], dtype=float
    )

    norm: Normalize
    positive = values[np.isfinite(values) & (values > 0)]
    if positive.size:
        vmin, vmax = float(positive.min()), float(positive.max())
        if vmin == vmax:
            vmax = vmin * 1.1
        norm = LogNorm(vmin=vmin, vmax=vmax)
    else:
        norm = Normalize(vmin=0.0, vmax=1.0)
    cmap = plt.get_cmap("viridis")

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = f"pmt_area_run_{run_id}"
    if index is not None:
        name += f"__{index}"
    path = out / f"{name}.png"

    fig, ax = plt.subplots(figsize=(7.5, 7.5))
    ax.add_patch(plt.Circle((0, 0), OUTER_RING_RADIUS_MM, facecolor="none",
                            edgecolor="0.2", linewidth=1.2))
    ax.add_patch(plt.Circle((0, 0), INNER_RING_RADIUS_MM, facecolor="none",
                            edgecolor="0.35", linewidth=1.0))
    for entry, value in zip(entries, values):
        color = (cmap(norm(float(value))) if np.isfinite(value) and value > 0
                 else (0.92, 0.92, 0.86, 1.0))
        llx = entry.x_mm - PMT_SQUARE_SIDE_MM / 2.0
        lly = entry.y_mm - PMT_SQUARE_SIDE_MM / 2.0
        ax.add_patch(Rectangle((llx, lly), PMT_SQUARE_SIDE_MM, PMT_SQUARE_SIDE_MM,
                               angle=PMT_CAD_ROTATION_DEG, rotation_point="center",
                               facecolor=color, edgecolor="black", linewidth=1.0,
                               zorder=3))
        ax.text(entry.x_mm, entry.y_mm, str(entry.pmt_no), ha="center",
                va="center", fontsize=9, zorder=4)

    cog = _weighted_center(by_id, charge_per_pmt)
    if cog is not None:
        ax.scatter([cog[0]], [cog[1]], marker="x", s=130, color="red",
                   linewidths=2.2, zorder=6)
        ax.text(cog[0], cog[1], " COG", color="red", fontsize=9, va="bottom",
                zorder=6)

    if values.size:
        mappable = ScalarMappable(norm=norm, cmap=cmap)
        mappable.set_array(values)
        fig.colorbar(mappable, ax=ax, pad=0.02, label="charge [arb.]")

    radius = OUTER_RING_RADIUS_MM
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-radius * 1.08, radius * 1.08)
    ax.set_ylim(-radius * 1.08, radius * 1.08)
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_title(title or f"PMT area map run {run_id} ({layout.source})")
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def _weighted_center(positions: Dict[str, Tuple[float, float]],
                     charge_per_pmt: Dict[str, float]) -> Optional[Tuple[float, float]]:
    """Weighted charge centre over pmt_ids present in both maps."""
    total = 0.0
    x_sum = 0.0
    y_sum = 0.0
    for pmt_id, weight in charge_per_pmt.items():
        pos = positions.get(pmt_id)
        if pos is None or not np.isfinite(weight) or weight <= 0:
            continue
        x_sum += pos[0] * weight
        y_sum += pos[1] * weight
        total += weight
    if total <= 0:
        return None
    return (x_sum / total, y_sum / total)
