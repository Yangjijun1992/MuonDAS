"""Persist peak-level summed waveforms (anode_sum / dynode_sum) to npz.

Storage layout (one file per run, no pickle needed):

    peaks_id        int64[n]
    anode_offsets   int64[n + 1]
    anode_data      float32[anode_offsets[-1]]
    dynode_offsets  int64[n + 1]
    dynode_data     float32[dynode_offsets[-1]]

Peak ``i`` has ``anode_data[anode_offsets[i]:anode_offsets[i + 1]]`` (empty when
the peak has no anode sum).  ``sum_ref`` is stored as an int64 scalar.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Sequence

import numpy as np


def save_sum_npz(
    path: str | Path,
    peaks_id: Sequence[int],
    anode_sums: Sequence[np.ndarray | None],
    dynode_sums: Sequence[np.ndarray | None],
    sum_ref: int = 50,
) -> None:
    """Write the per-peak sum waveforms to ``path`` (npz)."""
    ids = np.asarray(peaks_id, dtype=np.int64)

    def pack(arrs):
        offsets = np.zeros(len(arrs) + 1, dtype=np.int64)
        chunks: List[np.ndarray] = []
        for i, a in enumerate(arrs):
            offsets[i + 1] = offsets[i]
            if a is not None and len(a):
                chunk = np.asarray(a, dtype=np.float32)
                chunks.append(chunk)
                offsets[i + 1] = offsets[i] + len(chunk)
        data = np.concatenate(chunks) if chunks else np.zeros(0, dtype=np.float32)
        return offsets, data

    a_off, a_data = pack(anode_sums)
    d_off, d_data = pack(dynode_sums)
    np.savez_compressed(Path(path), peaks_id=ids, anode_offsets=a_off,
                        anode_data=a_data, dynode_offsets=d_off,
                        dynode_data=d_data, sum_ref=np.int64(sum_ref))


def load_sum_npz(path: str | Path) -> Dict[str, Any]:
    """Load a file written by :func:`save_sum_npz`.

    Returns ``{"peaks_id": int array, "sum_ref": int,
    "anode_sums": {peaks_id: array}, "dynode_sums": {peaks_id: array}}``;
    a peak without a side's sum maps to an empty array.
    """
    z = np.load(Path(path))
    ids = z["peaks_id"]
    a_off, d_off = z["anode_offsets"], z["dynode_offsets"]
    a_data, d_data = z["anode_data"], z["dynode_data"]
    return {
        "peaks_id": ids,
        "sum_ref": int(z["sum_ref"]),
        "anode_sums": {int(i): a_data[a_off[k]:a_off[k + 1]]
                       for k, i in enumerate(ids)},
        "dynode_sums": {int(i): d_data[d_off[k]:d_off[k + 1]]
                        for k, i in enumerate(ids)},
    }
