"""Physical pairing of S1 and S2 peak-level events.

For each ``S2`` event, look back a fixed time window (default 80 us) for an
unpaired ``S1``; if several are found, pick the one with the largest
``anode_sum_area``.  Each ``S1`` is used at most once.  ``S2`` events without a
match are isolated; ``S1`` events never matched are isolated.  Pairing is per
run (never across runs).
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def pair_s1_s2(
    events: pd.DataFrame,
    window_ns: float = 80000.0,
    signal_col: str = "signal_type",
    time_col: str = "peak_time_ns",
    size_col: str = "anode_sum_area",
    run_col: str = "run_id",
    id_col: str = "peaks_id",
) -> Dict[str, Any]:
    """Pair each S2 with the largest unpaired S1 within ``window_ns`` before it.

    Returns a dict with:
      - ``pairs``: DataFrame(run_id, s1_id, s2_id, dt_ns, s1_size)
      - ``isolated_s2``: DataFrame of unpaired S2 rows
      - ``isolated_s1``: DataFrame of unmatched S1 rows
    """
    s1 = events[events[signal_col] == "S1"].copy()
    s2 = events[events[signal_col] == "S2"].copy()

    pairs: List[dict] = []
    isolated_s2: List[int] = []
    used_s1: set = set()

    for rid in sorted(s2[run_col].unique()):
        s1r = s1[s1[run_col] == rid].sort_values(time_col)
        s2r = s2[s2[run_col] == rid].sort_values(time_col)
        if len(s1r) == 0:
            isolated_s2.extend(s2r[id_col].tolist())
            continue
        s1_t = s1r[time_col].to_numpy()
        s1_id = s1r[id_col].to_numpy()
        s1_sz = s1r[size_col].to_numpy()
        for _, row in s2r.iterrows():
            t = float(row[time_col])
            lo = np.searchsorted(s1_t, t - window_ns, side="left")
            hi = np.searchsorted(s1_t, t, side="right")
            cand = [i for i in range(lo, hi) if int(s1_id[i]) not in used_s1]
            if not cand:
                isolated_s2.append(int(row[id_col]))
                continue
            best = max(cand, key=lambda i: s1_sz[i])
            used_s1.add(int(s1_id[best]))
            pairs.append({
                run_col: int(rid),
                "s1_id": int(s1_id[best]),
                "s2_id": int(row[id_col]),
                "dt_ns": t - float(s1_t[best]),
                "s1_size": float(s1_sz[best]),
            })

    iso_s1 = s1[~s1[id_col].isin(used_s1)]
    return {
        "pairs": pd.DataFrame(pairs),
        "isolated_s2": s2[s2[id_col].isin(isolated_s2)],
        "isolated_s1": iso_s1,
    }


def pair_long_s2_with_s1(
    events: pd.DataFrame,
    window_ns: float = 25000.0,
    s2_width_min_ns: float = 10000.0,
    signal_col: str = "signal_type",
    time_col: str = "peak_time_ns",
    width_col: str = "width",
    size_col: str = "anode_sum_area",
    run_col: str = "run_id",
    id_col: str = "peaks_id",
) -> Dict[str, Any]:
    """Pair every **long** S2 with the largest unpaired S1 preceding it.

    A long S2 is an S2 event with ``width > s2_width_min_ns``; for each one the
    largest ``S1`` inside the ``window_ns`` window before it is taken (each S1
    used at most once, pairing is per run).  Returns:

      - ``pairs``: DataFrame(run_id, s1_id, s2_id, dt_ns, s1_size, s2_size,
        s2_width_ns)
      - ``paired_s2_ids``: DataFrame(run_id, peaks_id) of the matched S2
      - ``paired_s1_ids``: DataFrame(run_id, peaks_id) of the matched S1
      - ``n_long_s2``: number of long S2 considered
    """
    long_s2 = events[(events[signal_col] == "S2")
                     & (events[width_col] > s2_width_min_ns)].copy()
    s1 = events[events[signal_col] == "S1"].copy()

    pairs: List[dict] = []
    used_s1: set = set()
    used_s2: set = set()
    for rid in sorted(long_s2[run_col].unique()):
        s1r = s1[s1[run_col] == rid].sort_values(time_col)
        s2r = long_s2[long_s2[run_col] == rid].sort_values(time_col)
        if len(s1r) == 0:
            continue
        s1_t = s1r[time_col].to_numpy()
        s1_id = s1r[id_col].to_numpy()
        s1_sz = s1r[size_col].to_numpy()
        for _, row in s2r.iterrows():
            t = float(row[time_col])
            lo = int(np.searchsorted(s1_t, t - window_ns, side="left"))
            hi = int(np.searchsorted(s1_t, t, side="right"))
            cand = [i for i in range(lo, hi) if int(s1_id[i]) not in used_s1]
            if not cand:
                continue
            best = max(cand, key=lambda i: s1_sz[i])
            used_s1.add(int(s1_id[best]))
            used_s2.add(int(row[id_col]))
            pairs.append({
                run_col: int(rid),
                "s1_id": int(s1_id[best]),
                "s2_id": int(row[id_col]),
                "dt_ns": t - float(s1_t[best]),
                "s1_size": float(s1_sz[best]),
                "s2_size": float(row[size_col]),
                "s2_width_ns": float(row[width_col]),
            })

    p = pd.DataFrame(pairs)
    idf = pd.DataFrame({run_col: [], id_col: []})
    paired_s2 = (idf if p.empty
                 else p[[run_col, "s2_id"]].rename(columns={"s2_id": id_col}))
    paired_s1 = (idf if p.empty
                 else p[[run_col, "s1_id"]].rename(columns={"s1_id": id_col}))
    return {
        "pairs": p,
        "paired_s2_ids": paired_s2,
        "paired_s1_ids": paired_s1,
        "n_long_s2": int(len(long_s2)),
    }


def mark_paired_events(
    events: pd.DataFrame,
    window_ns: float = 25000.0,
    s2_width_min_ns: float = 10000.0,
    mark_col: str = "is_paired_event",
    run_col: str = "run_id",
    id_col: str = "peaks_id",
) -> tuple:
    """Flag peaks belonging to a long-S2 <-> S1 pair as **paired events**.

    These are *not* muon events: the pairing is consistent with random
    coincidence (see the pipeline doc).  Returns ``(events_with_flag,
    pairing_result)`` where the paired S2 and its matched S1 both get
    ``mark_col = True``; every other peak keeps ``False``.
    """
    out = events.copy()
    out[mark_col] = False
    res = pair_long_s2_with_s1(out, window_ns=window_ns,
                               s2_width_min_ns=s2_width_min_ns,
                               run_col=run_col, id_col=id_col)
    for ids in (res["paired_s2_ids"], res["paired_s1_ids"]):
        if len(ids):
            keys = set(zip(ids[run_col].astype(int), ids[id_col].astype(int)))
            mask = [k in keys for k in zip(out[run_col].astype(int),
                                           out[id_col].astype(int))]
            out.loc[mask, mark_col] = True
    return out, res
