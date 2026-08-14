"""Dynode-anode waveform clustering into time-window peaks.

Groups the matched pairs produced by
:func:`muon_analysis.matching.match_events` into
:class:`muon_analysis.models.Peak` clusters.  Pairs are processed in a single
sorted pass over dynode time; a new peak opens whenever a pair's dynode time
exceeds the current peak's anchor dynode time by more than
``clustering.window_ns`` (greedy, anchor-based grouping).
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from muon_analysis.models import Peak, PeakRecord


def _check_time_field(records: Any, side: str) -> None:
    """Raise a clear ValueError when ``records`` lacks a ``time`` field."""
    dtype = getattr(records, "dtype", None)
    fields = getattr(dtype, "names", None)
    if not fields or "time" not in fields:
        raise ValueError(
            f"{side} records missing required 'time' field; "
            "cannot cluster matched pairs by time window"
        )


def _record_times(records: Any) -> np.ndarray:
    """Return the ``time`` values of ``records`` as a float array."""
    return np.asarray(records["time"], dtype=float)


def _build_peak(
    peaks_id: int,
    anode: Dict[int, PeakRecord],
    dynode: Dict[int, PeakRecord],
    rows: List[int],
    channels: set,
    start: float,
    end: float,
) -> Peak:
    """Finalize a ``Peak`` from the accumulated per-peak state."""
    return Peak(
        peaks_id=peaks_id,
        start_time_ns=start,
        end_time_ns=end,
        anode_records=sorted(anode.values(), key=lambda r: r.record_id),
        dynode_records=sorted(dynode.values(), key=lambda r: r.record_id),
        match_rows=sorted(rows),
        channels=sorted(channels),
    )


def cluster_peaks(
    match_df: pd.DataFrame,
    run_data: Any,
    config: Dict[str, Any],
) -> List[Peak]:
    """Group matched pairs into peaks by time window.

    Parameters
    ----------
    match_df:
        DataFrame with columns ``[dynode_idx, anode_idx, dt, channel]`` where
        ``dynode_idx``/``anode_idx`` are positional indices into
        ``run_data.dynode_records`` / ``run_data.anode_records``.
    run_data:
        ``muon_analysis.io.data.RunData`` exposing ``dynode_records`` and
        ``anode_records`` (each with a ``time`` field in ns).
    config:
        Effective config dict; ``clustering.window_ns`` (default 100.0).
    """
    if len(match_df) == 0:
        return []

    window_ns = float(config.get("clustering", {}).get("window_ns", 100.0))

    dyn_records = run_data.dynode_records
    an_records = run_data.anode_records
    _check_time_field(dyn_records, "dynode")
    _check_time_field(an_records, "anode")
    dyn_times = _record_times(dyn_records)
    an_times = _record_times(an_records)

    pairs = match_df.reset_index(drop=True)
    # single-pass anchor grouping, ordered by dynode time
    pair_dyn_times = np.asarray(
        [dyn_times[int(i)] for i in pairs["dynode_idx"]], dtype=float
    )
    order = np.argsort(pair_dyn_times, kind="stable")
    sorted_pairs = pairs.iloc[order]

    peaks: List[Peak] = []
    cur_anode: Dict[int, PeakRecord] = {}
    cur_dynode: Dict[int, PeakRecord] = {}
    cur_rows: List[int] = []
    cur_channels: set = set()
    cur_start: float = 0.0
    cur_end: float = 0.0
    anchor_dyn_time: float | None = None

    for _, row in sorted_pairs.iterrows():
        d_idx = int(row["dynode_idx"])
        a_idx = int(row["anode_idx"])
        d_time = dyn_times[d_idx]
        a_time = an_times[a_idx]

        if anchor_dyn_time is None or d_time > anchor_dyn_time + window_ns:
            # close the previous peak and open a new one (this pair is the anchor)
            if anchor_dyn_time is not None:
                peaks.append(
                    _build_peak(len(peaks), cur_anode, cur_dynode, cur_rows,
                                 cur_channels, cur_start, cur_end)
                )
            cur_anode = {}
            cur_dynode = {}
            cur_rows = []
            cur_channels = set()
            cur_start = d_time
            cur_end = d_time
            anchor_dyn_time = d_time

        an_record = an_records[a_idx]
        a_rec_id = int(an_record["record_id"])
        if a_rec_id not in cur_anode:
            a_ch = int(an_record["channel"])
            cur_anode[a_rec_id] = PeakRecord(a_rec_id, a_ch, a_time, False)
            cur_channels.add(a_ch)
            cur_start = min(cur_start, a_time)
            cur_end = max(cur_end, a_time)

        d_record = dyn_records[d_idx]
        d_rec_id = int(d_record["record_id"])
        if d_rec_id not in cur_dynode:
            d_ch = int(d_record["channel"])
            cur_dynode[d_rec_id] = PeakRecord(d_rec_id, d_ch, d_time, True)
            cur_channels.add(d_ch)
            cur_start = min(cur_start, d_time)
            cur_end = max(cur_end, d_time)

        cur_rows.append(int(row.name))

    if anchor_dyn_time is not None:
        peaks.append(
            _build_peak(len(peaks), cur_anode, cur_dynode, cur_rows,
                         cur_channels, cur_start, cur_end)
        )

    return peaks
