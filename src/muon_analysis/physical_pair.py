"""Physical pairing of muon_s1 and muon_s2 peak-level events.

For each ``muon_s2`` event, look back a fixed time window (default 80 us) for
an unpaired ``muon_s1``; if several are found, pick the one with the largest
``anode_sum_area``.  Each ``muon_s1`` is used at most once.  ``muon_s2`` events
without a match are isolated; ``muon_s1`` events never matched are isolated.
Pairing is per run (never across runs).
"""
from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd


def pair_muon_s1_s2(
    events: pd.DataFrame,
    window_ns: float = 80000.0,
    signal_col: str = "signal_type",
    time_col: str = "peak_time_ns",
    size_col: str = "anode_sum_area",
    run_col: str = "run_id",
    id_col: str = "peaks_id",
) -> Dict[str, Any]:
    """Pair muon_s2 with the largest unpaired muon_s1 within ``window_ns`` before it.

    Returns a dict with:
      - ``pairs``: DataFrame(run_id, muon_s1_id, muon_s2_id, dt_ns, s1_size)
      - ``isolated_s2``: DataFrame of unpaired muon_s2 rows
      - ``isolated_s1``: DataFrame of unmatched muon_s1 rows
    """
    s1 = events[events[signal_col] == "muon_s1"].copy()
    s2 = events[events[signal_col] == "muon_s2"].copy()

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
                "muon_s1_id": int(s1_id[best]),
                "muon_s2_id": int(row[id_col]),
                "dt_ns": t - float(s1_t[best]),
                "s1_size": float(s1_sz[best]),
            })

    iso_s1 = s1[~s1[id_col].isin(used_s1)]
    return {
        "pairs": pd.DataFrame(pairs),
        "isolated_s2": s2[s2[id_col].isin(isolated_s2)],
        "isolated_s1": iso_s1,
    }
