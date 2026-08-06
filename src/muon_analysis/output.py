"""Result persistence: event-level CSV and waveform .npy clips.

CSV rows carry provenance columns (``parameter_version`` and
``gain_db_version``) for reproducibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd


def ensure_output_dir(output_dir: str | Path) -> Path:
    p = Path(output_dir)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _provenance(config: Dict[str, Any], gain_db_version: str,
                run_id: str) -> Dict[str, Any]:
    return {
        "run_id": run_id,
        "parameter_version": config.get("parameter_version", ""),
        "gain_db_version": gain_db_version,
    }


def candidates_to_dataframe(
    candidates: List[Any],
    config: Dict[str, Any],
    gain_db_version: str,
    run_id: str,
    offset: int = 0,
) -> pd.DataFrame:
    """Convert a candidate list into a flat DataFrame (one row per event)."""
    rows: List[Dict[str, Any]] = []
    prov = _provenance(config, gain_db_version, run_id)
    for i, cand in enumerate(candidates):
        row = cand.as_dict()
        row["event_id"] = offset + i
        row["run_id"] = prov["run_id"]
        row["parameter_version"] = prov["parameter_version"]
        row["gain_db_version"] = prov["gain_db_version"]
        rows.append(row)
    return pd.DataFrame(rows)


def save_events_csv(
    df: pd.DataFrame,
    output_dir: str | Path,
    run_id: str,
) -> Path:
    """Write an event-level CSV to ``output_dir/events_run_<run_id>.csv``."""
    ensure_output_dir(output_dir)
    path = Path(output_dir) / f"events_run_{run_id}.csv"
    df.to_csv(path, index=False)
    return path


def save_waveforms_npy(
    waveforms: np.ndarray,
    output_dir: str | Path,
    run_id: str,
) -> Path:
    """Save waveform clips as a .npy file (enabled via config)."""
    ensure_output_dir(output_dir)
    path = Path(output_dir) / f"waveforms_run_{run_id}.npz"
    extra = {
        "run_id": run_id,
        "shape": list(waveforms.shape) if hasattr(waveforms, "shape") else None,
    }
    np.savez(path, waveforms=waveforms, meta=extra)
    return path


def save_run_summary_metadata(
    output_dir: str | Path,
    run_id: str,
    metadata: Dict[str, Any],
) -> Path:
    ensure_output_dir(output_dir)
    path = Path(output_dir) / f"run_{run_id}_metadata.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, default=str)
    return path
