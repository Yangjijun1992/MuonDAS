"""Core data models used across the analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List


@dataclass
class RunInfo:
    """Metadata describing a single run.

    Mirrors the ``pmt_analysis.models.RunInfo`` shape used by the reference
    example scripts so their logic (raw_reader, runinfo) can be reused.
    """

    run_id: str
    runtype: str
    run_dir: Path
    runinfo_path: Path
    raw_dir: Path
    outfile_name: str = ""
    source: str = ""
    datatype: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def pmt_id_map(self) -> Dict[tuple, str]:
        """Mapping ``(board_id, channel) -> pmt_id`` from runinfo 'mapping'."""
        result: Dict[tuple, str] = {}
        raw_mapping = self.metadata.get("mapping")
        if not raw_mapping:
            return result
        for board_info in raw_mapping:
            board_id = board_info.get("board_id")
            for ch_info in board_info.get("channels", []):
                result[(board_id, ch_info.get("ch"))] = ch_info.get("pmt")
        return result
