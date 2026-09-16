"""Dynode-anode waveform clustering into time-window peaks.

Groups the matched pairs produced by
:func:`muon_analysis.matching.match_events` into
:class:`muon_analysis.models.Peak` clusters.  **Each matched anode/dynode
record is first passed through the pulse finder**; clustering then uses the
**pulse-start time** (``record.time + pulse_start_sample * sample_interval_ns``)
as the reference point, and a new peak opens whenever a pair's reference time
exceeds the current peak's anchor by more than ``clustering.window_ns``
(default 320 ns = 80 samples; greedy, anchor-based grouping).
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


def _pulse_start_reference_times(
    records: Any,
    idxs,
    invert: bool,
    accessor,
    config: Dict[str, Any],
    interval_ns: float,
) -> Dict[int, float]:
    """Reference time per record index = ``time + pulse_start * interval_ns``.

    Each record's waveform is passed through :func:`pulse_finder` (dynode
    waveforms are inverted first); records without a resolvable pulse fall back
    to their raw ``time``.
    """
    from muon_analysis.pulsefinding import pulse_finder

    ref: Dict[int, float] = {}
    for i in idxs:
        rec = records[i]
        rid = int(rec["record_id"])
        try:
            wf = np.asarray(accessor.signals([rid]).reshape(-1), dtype=float)
        except (KeyError, IndexError, ValueError):
            wf = np.array([])
        if len(wf) == 0:
            ref[i] = float(rec["time"])
            continue
        if invert:
            wf = -wf
        bounds = pulse_finder(wf, config)
        st = bounds[0] if bounds is not None else 0
        ref[i] = float(rec["time"]) + st * interval_ns
    return ref


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
    """Group matched pairs into peaks by the pulse-start time window.

    Each matched anode/dynode record is passed through the pulse finder; the
    clustering reference is the record's pulse-start time
    (``time + pulse_start_sample * sample_interval_ns``).  A new peak opens when
    a pair's reference time exceeds the current anchor by more than
    ``clustering.window_ns`` (default 320 ns).
    """
    if len(match_df) == 0:
        return []

    window_ns = float(config.get("clustering", {}).get("window_ns", 320.0))
    interval_ns = float(config.get("matching", {}).get("sample_interval_ns", 4.0))

    dyn_records = run_data.dynode_records
    an_records = run_data.anode_records
    _check_time_field(dyn_records, "dynode")
    _check_time_field(an_records, "anode")

    from muon_analysis.filtering import SignalAccessor
    accessor = SignalAccessor.from_run_data(run_data)

    pairs = match_df.reset_index(drop=True)
    an_ref = _pulse_start_reference_times(
        an_records, sorted({int(i) for i in pairs["anode_idx"]}),
        False, accessor, config, interval_ns)
    dyn_ref = _pulse_start_reference_times(
        dyn_records, sorted({int(i) for i in pairs["dynode_idx"]}),
        True, accessor, config, interval_ns)

    pair_ref = np.asarray(
        [min(an_ref[int(a)], dyn_ref[int(d)])
         for a, d in zip(pairs["anode_idx"], pairs["dynode_idx"])],
        dtype=float,
    )
    order = np.argsort(pair_ref, kind="stable")
    sorted_pairs = pairs.iloc[order]

    peaks: List[Peak] = []
    cur_anode: Dict[int, PeakRecord] = {}
    cur_dynode: Dict[int, PeakRecord] = {}
    cur_rows: List[int] = []
    cur_channels: set = set()
    cur_start: float = 0.0
    cur_end: float = 0.0
    anchor_ref: float | None = None

    for _, row in sorted_pairs.iterrows():
        d_idx = int(row["dynode_idx"])
        a_idx = int(row["anode_idx"])
        a_time = float(an_records[a_idx]["time"])
        d_time = float(dyn_records[d_idx]["time"])
        r_time = an_ref[a_idx]

        if anchor_ref is None or r_time > anchor_ref + window_ns:
            if anchor_ref is not None:
                peaks.append(
                    _build_peak(len(peaks), cur_anode, cur_dynode, cur_rows,
                                 cur_channels, cur_start, cur_end)
                )
            cur_anode = {}
            cur_dynode = {}
            cur_rows = []
            cur_channels = set()
            cur_start = a_time
            cur_end = a_time
            anchor_ref = r_time

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

    if anchor_ref is not None:
        peaks.append(
            _build_peak(len(peaks), cur_anode, cur_dynode, cur_rows,
                         cur_channels, cur_start, cur_end)
        )

    return peaks
