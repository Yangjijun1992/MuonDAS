"""Optional ``.npy`` / HDF5 readers for persisted/intermediate records.

These produce the same structured-records layout as the waveform_analysis
reader so downstream modules are format-agnostic.  Each file is expected to
contain a structured numpy array with at least the fields:
``time``, ``channel``, ``board``, ``record_id``, ``event_length``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, List

import numpy as np


class ReaderError(Exception):
    """Raised when an alternative reader fails to load data."""


def load_npy_records(paths: List[Path]) -> Any:
    """Load and concatenate structured records from ``.npy`` files."""
    arrays = []
    for p in paths:
        arr = np.load(p, allow_pickle=False)
        arrays.append(arr)
    if not arrays:
        return np.empty(0, dtype=[("time", "i8"), ("channel", "i4"),
                                  ("board", "i4"), ("record_id", "i8"),
                                  ("event_length", "i4")])
    records = np.concatenate(arrays)
    return records


def _h5_file_group(path: Path):
    import h5py
    f = h5py.File(path, "r")
    # prefer a top-level 'records' dataset if present, else search
    if "records" in f:
        return f, f["records"]
    for key in f.keys():
        obj = f[key]
        if hasattr(obj, "shape") and obj.dtype.names:
            return f, obj
    raise ReaderError(f"No structured records dataset found in {path}")


def load_h5_records(paths: List[Path]) -> Any:
    """Load and concatenate structured records from HDF5 files."""
    import importlib.util
    if importlib.util.find_spec("h5py") is None:
        raise ReaderError("h5py is required for HDF5 reading")

    arrays = []
    for p in paths:
        f, ds = _h5_file_group(p)
        try:
            arr = ds[:]
        finally:
            f.close()
        arrays.append(arr)
    if not arrays:
        return np.empty(0, dtype=[("time", "i8"), ("channel", "i4"),
                                  ("board", "i4"), ("record_id", "i8"),
                                  ("event_length", "i4")])
    return np.concatenate(arrays)


READERS = {
    "npy": load_npy_records,
    "hdf5": load_h5_records,
    "h5": load_h5_records,
}


def load_alt_records(paths: List[Path], file_format: str) -> Any:
    reader = READERS.get(file_format.lower())
    if reader is None:
        raise ReaderError(f"Unsupported file format: {file_format!r}")
    return reader(paths)
