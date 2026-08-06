"""Raw data readers.

Aligned with the reference ``examples/raw_reader.py`` which uses the
``waveform_analysis`` package to load V1725 binary data into structured
records (fields include ``time``, ``channel``, ``board``, ``record_id``,
``event_length``).  Optional ``npy`` / HDF5 readers are provided for
persisted / intermediate data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

from muon_analysis.io.data import RunData, split_by_board
from muon_analysis.models import RunInfo

DYNODE_BOARD = 1
ANODE_BOARD = 0


@dataclass
class RawDataBundle:
    """Unified container for loaded raw data."""

    runinfo: RunInfo
    source_path: List[Path]
    data: Any
    data_format: str
    event_count: int
    channel_count: int
    waveform_count: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class RawDataError(Exception):
    """Base error for raw data loading failures."""


def resolve_raw_input_path(runinfo: RunInfo) -> List[Path]:
    """Resolve raw binary file paths from ``runinfo.raw_dir``."""
    raw_dir = runinfo.raw_dir
    if not raw_dir.exists():
        raise FileNotFoundError(f"Raw directory not found: {raw_dir}")
    bin_files = sorted(raw_dir.glob("*_raw_*.bin"))
    if not bin_files:
        raise FileNotFoundError(
            f"No raw binary files (*_raw_*.bin) found in: {raw_dir}"
        )
    return bin_files


def load_raw_data_from_notebook_logic(
    input_paths: List[Path],
    runinfo: RunInfo,
) -> Any:
    """Load raw data using ``waveform_analysis`` records view.

    Requires the ``waveform_analysis`` package (pyth12 environment).
    """
    try:
        from waveform_analysis.core.context import Context
        from waveform_analysis.core import records_view
        from waveform_analysis.utils.formats import get_adapter
    except ImportError as e:
        raise ImportError(
            "waveform_analysis package is required for raw data loading. "
            f"Original error: {e}"
        ) from e

    storage_dir = str(runinfo.run_dir.parent) + "/"

    v1725_reader = get_adapter("v1725").format_reader
    if not hasattr(v1725_reader, "use_optimized"):
        raise RuntimeError("installed V1725 reader cannot select its parse path")
    v1725_reader.use_optimized = False

    ctx = Context(storage_dir=storage_dir)

    from waveform_analysis.core.plugins.plugin_sets import (
        plugins_io,
        plugins_waveform,
    )

    ctx.register(*plugins_io())
    ctx.register(*plugins_waveform())

    daq_adapter = runinfo.metadata.get("daq_adapter", "V1725").lower()
    ctx.set_config({
        "data_root": storage_dir,
        "daq_adapter": daq_adapter,
        "show_progress": False,
        "use_filtered": False,
        "wave_source": "records",
    })

    rv = records_view(ctx, runinfo.run_id)
    return rv


def summarize_raw_data(data: Any) -> Dict[str, Any]:
    """Extract summary statistics from loaded raw data."""
    records = data.records
    event_count = len(records)
    channel_count = len(set(records["channel"].tolist()))
    boards = sorted(set(records["board"].tolist()))

    time_min = int(records["time"].min())
    time_max = int(records["time"].max())
    daq_time_s = (time_max - time_min) * 1e-9

    event_lengths = records["event_length"]
    avg_waveform_length = float(event_lengths.mean()) if len(event_lengths) > 0 else 0

    return {
        "event_count": event_count,
        "channel_count": channel_count,
        "board_count": len(boards),
        "boards": boards,
        "waveform_count": event_count,
        "daq_time_s": daq_time_s,
        "avg_waveform_length": avg_waveform_length,
        "record_dtype_names": list(records.dtype.names or []),
    }


class NotebookBasedRawDataReader:
    """Raw data reader based on waveform_analysis notebook logic."""

    def __init__(self) -> None:
        self._data_cache: Dict[str, Any] = {}

    def read(self, runinfo: RunInfo) -> RawDataBundle:
        source_paths = resolve_raw_input_path(runinfo)
        rv = load_raw_data_from_notebook_logic(source_paths, runinfo)
        summary = summarize_raw_data(rv)
        return RawDataBundle(
            runinfo=runinfo,
            source_path=source_paths,
            data=rv,
            data_format="waveform_analysis_records",
            event_count=summary["event_count"],
            channel_count=summary["channel_count"],
            waveform_count=summary["waveform_count"],
            metadata=summary,
        )


def read_data(runinfo: RunInfo, data_format: str = "waveform_analysis_records",
              data_dir: str | Path | None = None) -> RunData:
    """High-level reader: load a run and split records by board.

    ``data_format`` selects the backend:
      - ``waveform_analysis_records`` (default; needs waveforms + signals)
      - ``npy`` / ``hdf5`` (alternative/offline persistence backends)
    """
    fmt = data_format.lower()

    if fmt in ("npy", "hdf5", "h5"):
        from muon_analysis.io.readers_alt import load_alt_records
        src_dir = Path(data_dir) if data_dir else runinfo.raw_dir
        files: List[Path] = []
        if fmt == "npy":
            for f in sorted(Path(src_dir).glob("*.npy")):
                if "_waveforms" not in f.name:
                    files.append(f)
        else:
            for pat in ("*.h5", "*.hdf5"):
                files.extend(sorted(Path(src_dir).glob(pat)))
        if not files:
            raise FileNotFoundError(
                f"No {fmt} records files found in {src_dir}"
            )
        records = load_alt_records(files, fmt)
        metadata = {
            "source_files": [str(f) for f in files],
            "record_dtype_names": list(records.dtype.names or []),
        }

        # Optional co-located waveforms (shape (N, T)) aligned to records order.
        waves = _load_waveforms_from_dir(Path(src_dir), len(records))
        data = SimpleNamespace(records=records, signals=None)
        if waves is not None:
            wf_map = {int(data_rid): waves[i] for i, data_rid in
                      enumerate(records["record_id"])}
            data.signals = lambda ids, _m=wf_map: np.stack(
                [_m[int(i)] for i in np.asarray(ids)]
            )

        dynode, anode = split_by_board(records)
        return RunData(runinfo=runinfo, data=data, dynode_records=dynode,
                       anode_records=anode, data_format=fmt, metadata=metadata)

    # waveform_analysis_records backend
    bundle = NotebookBasedRawDataReader().read(runinfo)
    records = bundle.data.records
    dynode, anode = split_by_board(records)
    return RunData(runinfo=runinfo, data=bundle.data, dynode_records=dynode,
                   anode_records=anode, data_format=bundle.data_format,
                   metadata=bundle.metadata)


def _load_waveforms_from_dir(src_dir: Path, n_records: int):
    """Load co-located waveforms (N, T) if a `*_waveforms.npy` is present."""
    candidates = sorted(src_dir.glob("*_waveforms.npy"))
    if not candidates:
        return None
    arr = np.load(candidates[0], allow_pickle=False)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.shape[0] < n_records:
        return None
    return arr


from types import SimpleNamespace
