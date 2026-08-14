"""Configuration loading, defaults and validation.

All tunable parameters (filter thresholds, matching windows, integration
window strategy, gain DB path, ...) are managed via YAML config files.
Override precedence: CLI > user config file > built-in defaults.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "analysis.yaml"

# Deep-copied defaults so callers can't accidentally mutate shared state.
_DEFAULTS: Dict[str, Any] = {
    "parameter_version": "0.1.0",
    "progress": True,  # tqdm progress bars in the pipeline
    "data_source": {
        "data_root": "/mnt/data/TPC",
        "data_format": "waveform_analysis_records",
        "data_dir": None,
    },
    "runinfo": {
        # Explicit runtype to scope search: '' => auto-discover by probing
        # candidate runtype dirs under data_root (e.g. run6_Xe, run_R8520...).
        "runtype": "",
        # Optional restricted list of runtype names to probe (auto-discovery).
        "runtype_candidates": [],
        "run_tag": "pmt test",
    },
    "matching": {
        "sample_interval_ns": 4,
        "dynode_shift_ns": 6,
        "match_window_ns": [0, 40],
        "min_diff_ns": 0,
        "max_diff_ns": 40,
        "channel_delay_ns": {},
    },
    "clustering": {
        "window_ns": 100,
    },
    "pulse_finder": {
        # Negative-pulse boundary finder (borrowed from pmt_analysis
        # findpulse_st_ed, extended for clipped plateaus).  Dynode waveforms
        # are inverted before searching.
        "baseline_samples": 30,      # samples used for baseline estimate
        "height_threshold": 10.0,    # ADC: pulse rejected below this height
        "min_recovery_frac": 0.3,    # min recovery rise (frac of height) to accept
        "end_baseline_tol": 20.0,    # ADC: end must be within this of baseline
        "end_consecutive": 3,        # samples AFTER the end that must stay within tol
    },
    "filtering": {
        "signal_positive_polarity": {"asym_min": 0.7, "height_min": None, "height_max": None},
        "signal_negative_polarity": {"asym_min": 0.7, "height_min": None, "height_max": None},
        "min_event_length": 7000,
        "min_seg_area_pe": 20000,
        "height_min": None,          # peak-level amplitude bounds
        "height_max": None,
        "width_min": None,
        "width_max": None,
        "rise_time_max": None,
        "min_area_pe_anode": None,
        "min_area_pe_dynode": None,
    },
    "features": {
        "integral_window_mode": "fixed",
        "integral_start": 20,
        "integral_end": 100,
        "baseline_samples": 10,
        "rise_time_low": 0.1,
        "rise_time_high": 0.9,
    },
    "gain_db": {
        "backend": "pmtdata",
        "run_id": "00179",
        "sqlite_path": "",
        "csv_path": "",
    },
    "output": {
        "output_dir": "output",
        "save_waveforms": True,
        "save_plots": True,
        "cache_dir": "/mnt/data/tmp/muon_analysis",
    },
    "plotting": {
        "backend": "Agg",
        "dynode_scale": 110,
        "dynode_lp_cutoff_hz": None,   # None=no low-pass on compare dynode; e.g. 45e6
        "plot_len": 100,
        "cutoff_hz": 20e6,
        "fs": 250e6,
        "sample_interval_ns": 4,
        "num_samples": 3,
    },
    "cog": {
        "pattern_path": "",          # empty => try runinfo pos / fallback
        "pattern_format": "auto",    # auto | json | csv | yaml
        "charge_source": "anode",    # anode | dynode  (which side's charge feeds COG)
        "use_fallback": False,       # use built-in 7-PMT fallback geometry when no other source
    },
    "track": {
        "slice_us": 1.0,             # time-slice width for track reconstruction
        "fs": 250e6,                 # sample rate (Hz) for waveform time slicing
        "save_plots": True,          # save per-candidate 3D track PNGs
    },
}


class ConfigError(Exception):
    """Raised for invalid configuration."""


def _deep_merge(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Recursively merge ``override`` onto a copy of ``base``."""
    if not override:
        return copy.deepcopy(base)
    result = copy.deepcopy(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_yaml(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _validate(config: Dict[str, Any]) -> None:
    features = config["features"]
    mode = features.get("integral_window_mode", "fixed")
    if mode not in ("fixed", "peak_finder"):
        raise ConfigError(f"Unsupported integral_window_mode: {mode!r}")
    if mode == "fixed":
        start = features.get("integral_start")
        end = features.get("integral_end")
        if start is None or end is None:
            raise ConfigError("fixed integral window requires integral_start/end")
        if start >= end:
            raise ConfigError(
                f"invalid integral window: start={start} >= end={end}"
            )

    gain_backend = config["gain_db"].get("backend")
    if gain_backend not in ("pmtdata", "sqlite", "csv"):
        raise ConfigError(f"Unsupported gain_db.backend: {gain_backend!r}")


def _normalize(config: Dict[str, Any]) -> None:
    """Coerce string-typed numeric YAML values (e.g. ``'45e6'``) to floats."""
    plot = config.get("plotting", {})
    for key in ("dynode_lp_cutoff_hz", "cutoff_hz", "fs"):
        val = plot.get(key)
        if isinstance(val, str):
            plot[key] = float(val)


def build_config(
    config_path: Optional[str | Path] = None,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the effective configuration dict.

    Parameters
    ----------
    config_path:
        Optional path to a user YAML config. If omitted, the packaged default
        config file is loaded (if present), otherwise built-in defaults.
    overrides:
        Optional dict of leaf overrides (e.g. from CLI), merged last.
    """
    base = copy.deepcopy(_DEFAULTS)
    if config_path is None:
        if DEFAULT_CONFIG_PATH.exists():
            base = _deep_merge(base, load_yaml(DEFAULT_CONFIG_PATH))
    else:
        base = _deep_merge(base, load_yaml(config_path))
    base = _deep_merge(base, overrides)
    _normalize(base)
    _validate(base)
    return base


def param_hash(config: Dict[str, Any]) -> str:
    """Stable SHA-1 hash of the processing parameters (for cache keys).

    Excludes volatile fields (output_dir, cache_dir, save_* flags) so that
    results are identical under the same physical processing parameters.
    """
    stable = copy.deepcopy(config)
    output = stable.get("output", {})
    output.pop("output_dir", None)
    output.pop("cache_dir", None)
    output.pop("save_waveforms", None)
    output.pop("save_plots", None)
    blob = json.dumps(stable, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def get(cfg: Dict[str, Any], dotted: str, default: Any = None) -> Any:
    """Small dot-path getter, e.g. ``get(cfg, 'matching.max_diff_ns')``."""
    node: Any = cfg
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
