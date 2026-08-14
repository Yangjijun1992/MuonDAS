"""Dynode-anode high-precision time matching.

Aligned with the reference notebook logic:
  - apply a global time shift to dynode records (``shift_time_records``,
    configured via ``matching.dynode_shift_ns``, default 6 ns) to correct
    channel delay;
  - match anode & dynode per-channel using pandas ``merge_asof`` with
    ``direction='backward'``;
  - keep pairs whose ``dt = t_dyn - t_ano`` lies within a window.

Per-channel delay calibration is supported via the config
``matching.channel_delay_ns`` map.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np
import pandas as pd


class MatchedEvent:
    """A single dynode-anode matched pair (original record indices)."""

    __slots__ = ("dynode_idx", "anode_idx", "dt_ns", "channel")

    def __init__(self, dynode_idx, anode_idx, dt_ns, channel):
        self.dynode_idx = dynode_idx
        self.anode_idx = anode_idx
        self.dt_ns = dt_ns
        self.channel = channel

    def as_tuple(self):
        return (self.dynode_idx, self.anode_idx, self.dt_ns, self.channel)


def shift_time_records(records, shift_ns: float = 6.0):
    """Add ``shift_ns`` to the ``time`` field (in place)."""
    records["time"] = records["time"] + shift_ns
    return records


def get_matched_indices_by_channel(
    raw_rec_ano,
    raw_rec_dyn,
    min_diff: float = 0.0,
    max_diff: float = 30.0,
) -> pd.DataFrame:
    """Match anode & dynode records (per-channel, backward asof).

    Returns a DataFrame with columns ``[dynode_idx, anode_idx, dt, channel]``
    whose rows satisfy ``min_diff <= dt <= max_diff``.
    """
    a_df = pd.DataFrame({
        "time": np.asarray(raw_rec_ano["time"], dtype=float),
        "channel": np.asarray(raw_rec_ano["channel"]),
        "idx_ano": np.arange(len(raw_rec_ano)),
    })
    d_df = pd.DataFrame({
        "time": np.asarray(raw_rec_dyn["time"], dtype=float),
        "channel": np.asarray(raw_rec_dyn["channel"]),
        "idx_dyn": np.arange(len(raw_rec_dyn)),
    })

    a_df = a_df.sort_values("time")
    d_df = d_df.sort_values("time")

    matched = pd.merge_asof(
        d_df.rename(columns={"time": "t_dyn"}),
        a_df.rename(columns={"time": "t_ano"}),
        left_on="t_dyn",
        right_on="t_ano",
        by="channel",
        direction="backward",
    )

    matched["dt"] = matched["t_dyn"] - matched["t_ano"]
    mask = (matched["dt"] >= min_diff) & (matched["dt"] <= max_diff)
    final_pairs = matched[mask].dropna(subset=["idx_ano"]).copy()

    final_pairs["anode_idx"] = final_pairs["idx_ano"].astype(int)
    final_pairs["dynode_idx"] = final_pairs["idx_dyn"].astype(int)
    return final_pairs[["dynode_idx", "anode_idx", "dt", "channel"]]


def _apply_channel_delays(raw_rec_dyn, delay_map: Dict[int, float]):
    """Apply per-channel delay calibration to dynode times (ns)."""
    if not delay_map:
        return raw_rec_dyn
    offsets = np.asarray(
        [delay_map.get(int(ch), 0.0) for ch in raw_rec_dyn["channel"]],
        dtype=float,
    )
    raw_rec_dyn["time"] = raw_rec_dyn["time"] + offsets
    return raw_rec_dyn


def match_events(
    run_data,
    config: Dict[str, Any],
) -> pd.DataFrame:
    """High level matcher: dynode shift -> per-channel delay -> merge_asof.

    Parameters
    ----------
    run_data: :class:`muon_analysis.io.data.RunData`
        Must expose ``dynode_records`` and ``anode_records`` structured arrays.
    config:
        Effective config dict (see ``muon_analysis.config``).

    Returns
    -------
    pandas.DataFrame with columns ``[dynode_idx, anode_idx, dt, channel]``.
    """
    matching_cfg = config.get("matching", {})
    base_shift = float(matching_cfg.get("dynode_shift_ns", 6.0))
    min_diff = float(matching_cfg.get("min_diff_ns", 0))
    max_diff = float(matching_cfg.get("max_diff_ns", 30))
    delay_map = matching_cfg.get("channel_delay_ns", {}) or {}

    dynode_records = np.copy(run_data.dynode_records)
    anode_records = run_data.anode_records

    # global dynode time shift + per-channel delay calibration
    dynode_records = shift_time_records(dynode_records, base_shift)
    dynode_records = _apply_channel_delays(dynode_records, delay_map)

    return get_matched_indices_by_channel(
        anode_records, dynode_records, min_diff=min_diff, max_diff=max_diff
    )
