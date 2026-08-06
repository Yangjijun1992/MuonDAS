"""Cache management for intermediate processed data.

Caches preprocessed data (e.g. matched event structures) under
``/tmp/muon_analysis/`` keyed by ``<run_id>_<param_hash>`` so the same
conditions produce identical results and avoid recomputation.
"""

from __future__ import annotations

import json
import shutil
import warnings
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from muon_analysis.config import param_hash

DEFAULT_CACHE_DIR = Path("/tmp/muon_analysis")


class CacheWarning(UserWarning):
    """Emitted when cache space is low / cache directory unavailable."""


def cache_dir_for(config: Dict[str, Any]) -> Path:
    return Path(config.get("output", {}).get("cache_dir", DEFAULT_CACHE_DIR))


def cache_key(run_id: str, config: Dict[str, Any]) -> str:
    """Cache key = ``{run_id}__{param_hash}``."""
    return f"{run_id}__{param_hash(config)}"


def cache_path(run_id: str, config: Dict[str, Any], ext: str = ".npy") -> Path:
    return cache_dir_for(config) / (cache_key(run_id, config) + ext)


def write_npy(run_id: str, config: Dict[str, Any], arr: np.ndarray,
              ext: str = ".npy") -> Path:
    directory = cache_dir_for(config)
    ensure_cache_ready(directory)
    path = cache_path(run_id, config, ext)
    np.save(path, arr)
    return path


def read_npy(run_id: str, config: Dict[str, Any], ext: str = ".npy") -> Optional[np.ndarray]:
    path = cache_path(run_id, config, ext)
    if path.exists():
        return np.load(path, allow_pickle=False)
    return None


def write_json(run_id: str, config: Dict[str, Any], obj: Any,
               ext: str = ".json") -> Path:
    directory = cache_dir_for(config)
    ensure_cache_ready(directory)
    path = cache_path(run_id, config, ext)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, default=str)
    return path


def read_json(run_id: str, config: Dict[str, Any], ext: str = ".json") -> Optional[Any]:
    path = cache_path(run_id, config, ext)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def ensure_cache_ready(directory: Path) -> None:
    """Create the cache directory, warning if space is low (never auto-clear)."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        warnings.warn(f"Cannot create cache dir {directory}: {e}", CacheWarning)
        return
    try:
        usage = shutil.disk_usage(directory)
        free_gb = usage.free / 1e9
        if free_gb < 1.0:
            warnings.warn(
                f"Low disk space: {free_gb:.2f} GB free in {directory}",
                CacheWarning,
            )
    except OSError:
        pass


def list_cache(config: Dict[str, Any]) -> list:
    """List cache entries: (path, size, key, run_id, hash)."""
    directory = cache_dir_for(config)
    entries = []
    if not directory.exists():
        return entries
    for p in sorted(directory.iterdir()):
        if p.is_file():
            entries.append({
                "path": str(p),
                "size_bytes": p.stat().st_size,
                "stem": p.stem,
            })
    return entries


def show_cache(config: Dict[str, Any], verbose: bool = True) -> None:
    entries = list_cache(config)
    if not entries:
        print("Cache is empty.")
        return
    print(f"Cache entries ({len(entries)}) in {cache_dir_for(config)}:")
    for e in entries:
        if verbose:
            print(f"  {e['stem']}  ({e['size_bytes']} B) -> {e['path']}")
        else:
            print(f"  {e['path']}")


def clear_cache(config: Dict[str, Any]) -> int:
    """Remove all files under the cache dir; returns count removed."""
    directory = cache_dir_for(config)
    if not directory.exists():
        return 0
    removed = 0
    for p in directory.iterdir():
        if p.is_file() and not p.name.startswith("."):
            p.unlink()
            removed += 1
    return removed
