"""Structured data container for a single run, split by board."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from muon_analysis.models import RunInfo

DYNODE_BOARD = 1
ANODE_BOARD = 0


@dataclass
class RunData:
    """A loaded run with dynode/anode records separated by board.

    ``data`` holds the underlying records object exposing ``records`` and
    ``signals(record_ids)`` (the waveform_analysis records view), or a plain
    structured array for the npy/HDF5 backends.
    """

    runinfo: RunInfo
    data: Any
    dynode_records: Any
    anode_records: Any
    data_format: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def signals(self):
        """Return the signal-accessor bound to the underlying data."""
        if hasattr(self.data, "signals"):
            return self.data.signals
        return None


def split_by_board(records: Any) -> tuple:
    """Split records by board; returns ``(dynode_records, anode_records)``."""
    dynode = records[records["board"] == DYNODE_BOARD]
    anode = records[records["board"] == ANODE_BOARD]
    return dynode, anode
