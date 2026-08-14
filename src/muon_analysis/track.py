"""Muon track reconstruction from time-sliced dynode charges."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple

import numpy as np

from muon_analysis.cog import cog_reconstruct
from muon_analysis.filtering import SignalAccessor
from muon_analysis.models import Peak
from muon_analysis.plotting.waveforms import apply_lowpass_filter

__all__ = [
    "Track3D",
    "slice_peak_waveforms",
    "reconstruct_track",
    "plot_track",
]

DYNODE_BOARD = 1


@dataclass
class Track3D:
    """A reconstructed 3D muon track as per-slice (x, y) centres over time."""

    peaks_id: int
    slice_centers: List[Tuple[float, float]]  # (x, y) per slice
    slice_times_ns: List[float]

    @property
    def n_slices(self) -> int:
        return len(self.slice_centers)


def slice_peak_waveforms(peak: Peak, run_data, config) -> List[Dict[str, Any]]:
    """Slice each dynode record waveform into fixed-width time bins.

    Bins are aligned to the peak's earliest dynode record time. Returns a
    list of ``{"slice_index", "time_ns", "charge_per_channel"}`` dicts, one
    per bin that contains any charge.
    """
    slice_us = float((config.get("track") or {}).get("slice_us", 1.0))
    fs = float((config.get("track") or {}).get("fs", 250e6))
    plotting = config.get("plotting") or {}
    dynode_scale = float(plotting.get("dynode_scale", 110))
    lp_cutoff_hz = plotting.get("dynode_lp_cutoff_hz", None)

    if not peak.dynode_records:
        return []

    peak_start_ns = min(rec.time_ns for rec in peak.dynode_records)
    slice_ns = slice_us * 1000.0
    dt_ns = 1e9 / fs

    # Accumulate charge per (slice_index, channel).
    accum: Dict[int, Dict[int, float]] = {}
    accessor = SignalAccessor.from_run_data(run_data)
    for rec in peak.dynode_records:
        wf = np.asarray(accessor.signals([rec.record_id])[0], dtype=float)
        if lp_cutoff_hz is not None:
            wf = apply_lowpass_filter(wf, cutoff_hz=lp_cutoff_hz, fs=fs)
        wf = wf * dynode_scale
        t0 = rec.time_ns
        for j, val in enumerate(wf):
            t = t0 + j * dt_ns
            k = int((t - peak_start_ns) // slice_ns)
            if k < 0:
                continue
            accum.setdefault(k, {}).setdefault(rec.channel, 0.0)
            accum[k][rec.channel] += val

    slices = []
    for k in sorted(accum):
        charge = accum[k]
        if not any(charge.values()):
            continue
        slices.append({
            "slice_index": k,
            "time_ns": peak_start_ns + k * slice_ns,
            "charge_per_channel": charge,
        })
    return slices


def reconstruct_track(slice_data, runinfo, pattern, config) -> Track3D:
    """Reconstruct a :class:`Track3D` from sliced dynode charges."""
    pmt_id_map = runinfo.pmt_id_map
    centers: List[Tuple[float, float]] = []
    times: List[float] = []
    peaks_id = None
    for sl in slice_data:
        charge_per_pmt: Dict[str, float] = {}
        for ch, charge in sl["charge_per_channel"].items():
            pmt = pmt_id_map.get((DYNODE_BOARD, ch))
            if pmt is not None:
                charge_per_pmt[pmt] = charge_per_pmt.get(pmt, 0.0) + charge
        try:
            x, y = cog_reconstruct(charge_per_pmt, pattern)
        except ValueError:
            continue
        centers.append((x, y))
        times.append(sl["time_ns"])
        if peaks_id is None:
            peaks_id = sl.get("peaks_id")
    if peaks_id is None:
        peaks_id = slice_data[0].get("peaks_id") if slice_data else 0
    return Track3D(peaks_id=peaks_id, slice_centers=centers, slice_times_ns=times)


def plot_track(track3d: Track3D, output_dir, run_id, slice_us=1.0) -> Path:
    """Plot slice centres (x, y, time) connected by a line; save a PNG."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"track_run_{run_id}.png"

    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection="3d")
    xs = [c[0] for c in track3d.slice_centers]
    ys = [c[1] for c in track3d.slice_centers]
    ts = track3d.slice_times_ns
    ax.plot(xs, ys, ts, marker="o", linestyle="-", color="crimson")
    ax.set_xlabel("x")
    ax.set_ylabel("y")
    ax.set_zlabel("time [ns]")
    ax.set_title(f"Muon track run {run_id}")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
