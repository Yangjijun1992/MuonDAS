"""PMT-pattern loading and centre-of-gravity (COG) position reconstruction.

Pattern sources (reference ``xihu_fast_analysis/layout.py`` conventions):
  1. explicit pattern file (``cog.pattern_path``; JSON/CSV/YAML);
  2. positions embedded in the runinfo mapping (``channel["pos"]``);
  3. built-in fallback geometry (``FALLBACK_ENTRIES``, enabled via
     ``cog.use_fallback``).

Geometry is pure 2D (x_mm, y_mm) — the reference layout has no z coordinate.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Tuple

import yaml

from muon_analysis.models import PeakFeatures

__all__ = [
    "PmtEntry",
    "PmtLayout",
    "FALLBACK_ENTRIES",
    "load_pmt_pattern",
    "load_pmt_layout",
    "cog_reconstruct",
    "cog_reconstruct_peak",
]

# Fallback 7-PMT geometry (reference Xihu TPC layout, all anode readout).
FALLBACK_ENTRIES = [
    {"pmt_no": 1, "pmt_id": "LV2389", "label": "Upper left",
     "x_mm": -26.8, "y_mm": 17.7, "board_id": 0, "channel_id": 15},
    {"pmt_no": 2, "pmt_id": "LV2387", "label": "Top",
     "x_mm": -1.9, "y_mm": 32.0, "board_id": 0, "channel_id": 14},
    {"pmt_no": 3, "pmt_id": "LV2380", "label": "Lower left",
     "x_mm": -24.9, "y_mm": -14.4, "board_id": 0, "channel_id": 13},
    {"pmt_no": 4, "pmt_id": "LV2332", "label": "Center",
     "x_mm": 0.0, "y_mm": 0.0, "board_id": 0, "channel_id": 12},
    {"pmt_no": 5, "pmt_id": "LV2391", "label": "Upper right",
     "x_mm": 24.9, "y_mm": 14.4, "board_id": 0, "channel_id": 11},
    {"pmt_no": 6, "pmt_id": "LV2364", "label": "Bottom",
     "x_mm": 1.9, "y_mm": -32.0, "board_id": 0, "channel_id": 10},
    {"pmt_no": 7, "pmt_id": "LV2319", "label": "Lower right",
     "x_mm": 26.8, "y_mm": -17.7, "board_id": 0, "channel_id": 9},
]

_FALLBACK_BY_PMT_ID = {e["pmt_id"]: e for e in FALLBACK_ENTRIES}


@dataclass(frozen=True)
class PmtEntry:
    """One PMT position/readout entry (pure 2D geometry)."""

    pmt_id: str
    x_mm: float
    y_mm: float
    pmt_no: int = 0
    board_id: int = 0
    channel_id: int = 0
    signal: str = ""
    polarity: str = ""
    label: str = ""
    gain: float = 0.0

    @property
    def xy_mm(self):
        return (self.x_mm, self.y_mm)


@dataclass(frozen=True)
class PmtLayout:
    """Collection of PMT entries with lookup helpers."""

    entries: tuple
    source: str
    run_id: str = ""

    @property
    def pmt_positions_by_id(self) -> Dict[str, Tuple[float, float]]:
        """pmt_id -> (x_mm, y_mm), usable directly as a COG pattern dict."""
        return {e.pmt_id: (e.x_mm, e.y_mm) for e in self.entries}

    @property
    def channels_by_board(self) -> Dict[Tuple[int, int], PmtEntry]:
        return {(e.board_id, e.channel_id): e for e in self.entries}

    def entry_for_pmt(self, pmt_id: str) -> PmtEntry:
        for e in self.entries:
            if e.pmt_id == pmt_id:
                return e
        raise KeyError(f"Unknown PMT id: {pmt_id}")

    def entry_for_readout(self, board_id, channel_id) -> PmtEntry | None:
        return self.channels_by_board.get((int(board_id), int(channel_id)))


def _entry_from_channel(readout: Dict[str, Any], channel: Dict[str, Any]) -> PmtEntry | None:
    """Build a PmtEntry from a runinfo mapping channel, or None when the
    channel carries no resolvable position (no ``pos`` and no pmt_id fallback).
    """
    pmt_id = channel.get("pmt") or channel.get("pmt_id") or ""
    pos = channel.get("pos")
    fallback = _FALLBACK_BY_PMT_ID.get(pmt_id) if pmt_id else None
    if pos is None or len(pos) < 2:
        if fallback is None:
            return None
        x_mm, y_mm = fallback["x_mm"], fallback["y_mm"]
    else:
        x_mm, y_mm = float(pos[0]), float(pos[1])
    pmt_no = channel.get("pmt_no")
    if pmt_no is None:
        pmt_no = fallback["pmt_no"] if fallback is not None else 0
    return PmtEntry(
        pmt_id=pmt_id,
        x_mm=x_mm,
        y_mm=y_mm,
        pmt_no=int(pmt_no),
        board_id=int(readout.get("board_id", 0)),
        channel_id=int(channel.get("ch", -1)),
        signal=readout.get("signal") or "",
        polarity=readout.get("polarity") or (fallback or {}).get("polarity", ""),
        label=channel.get("label") or (fallback or {}).get("label", ""),
        gain=float(channel.get("gain") or readout.get("gain") or 0.0),
    )


def _layout_from_runinfo(runinfo) -> PmtLayout | None:
    """Build a layout from ``runinfo.metadata["mapping"]`` channel positions."""
    mapping = (runinfo.metadata or {}).get("mapping") if runinfo is not None else None
    if not mapping:
        return None
    entries = []
    for readout in mapping:
        for channel in readout.get("channels", []) or []:
            entry = _entry_from_channel(readout, channel)
            if entry is not None:
                entries.append(entry)
    if not entries:
        return None
    return PmtLayout(
        entries=tuple(sorted(entries, key=lambda e: e.pmt_no)),
        source="runinfo",
        run_id=getattr(runinfo, "run_id", ""),
    )


def _layout_from_file(path: str | Path, fmt: str = "auto") -> PmtLayout:
    """Build a layout from an explicit pattern file (pmt_id -> [x, y])."""
    pattern = load_pmt_pattern(path, fmt=fmt)
    entries = []
    for idx, (pmt_id, xyz) in enumerate(sorted(pattern.items()), start=1):
        entries.append(PmtEntry(pmt_id=pmt_id, x_mm=float(xyz[0]),
                                y_mm=float(xyz[1]), pmt_no=idx))
    return PmtLayout(entries=tuple(entries), source="file")


def _layout_from_fallback() -> PmtLayout:
    return PmtLayout(entries=tuple(PmtEntry(**e) for e in FALLBACK_ENTRIES),
                     source="fallback")


def load_pmt_layout(config, runinfo=None) -> PmtLayout | None:
    """Load the PMT layout following the reference precedence.

    Priority: explicit ``cog.pattern_path`` file > runinfo mapping positions >
    built-in fallback (only when ``cog.use_fallback`` is true).
    Returns None when no source yields a layout.
    """
    pattern_path = (config.get("cog") or {}).get("pattern_path", "")
    if pattern_path:
        return _layout_from_file(pattern_path,
                                 fmt=(config.get("cog") or {}).get(
                                     "pattern_format", "auto"))
    layout = _layout_from_runinfo(runinfo)
    if layout is not None:
        return layout
    if (config.get("cog") or {}).get("use_fallback", False):
        return _layout_from_fallback()
    return None


def _parse_entry(pmt_id: Any, pos: Any) -> Tuple[str, Tuple[float, float, float]]:
    """Normalise one ``(pmt_id, pos)`` pair into ``(str_id, (x, y, z))``."""
    key = str(pmt_id)
    xyz = list(pos)
    if len(xyz) == 2:
        xyz = [float(xyz[0]), float(xyz[1]), 0.0]
    elif len(xyz) == 3:
        xyz = [float(xyz[0]), float(xyz[1]), float(xyz[2])]
    else:
        raise ValueError(f"pmt pattern entry for {key!r} has {len(xyz)} coords; expected 2 or 3")
    return key, (xyz[0], xyz[1], xyz[2])


def _parse_json_or_yaml(loaded: Any) -> Dict[str, Tuple[float, float, float]]:
    """Normalise a JSON/YAML payload (dict or list-of-records) to a pattern."""
    pattern: Dict[str, Tuple[float, float, float]] = {}
    if isinstance(loaded, dict):
        items = loaded.items()
    elif isinstance(loaded, list):
        items = []
        for rec in loaded:
            if not isinstance(rec, dict):
                raise ValueError("pmt pattern list entries must be dicts with keys pmt_id/x/y/z")
            keys = set(rec)
            if "pmt_id" not in keys or not ({"x", "y"} <= keys):
                raise ValueError(f"pmt pattern entry missing pmt_id/x/y: {rec!r}")
            items.append((rec["pmt_id"], [rec["x"], rec["y"], rec.get("z", 0.0)]))
    else:
        raise ValueError(f"unsupported pmt pattern payload type: {type(loaded).__name__}")

    for pmt_id, pos in items:
        key, xyz = _parse_entry(pmt_id, pos)
        pattern[key] = xyz
    if not pattern:
        raise ValueError("pmt pattern is empty")
    return pattern


def _load_json(path: Path) -> Dict[str, Tuple[float, float, float]]:
    """Load and normalise a JSON pmt-pattern file."""
    with open(path, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    return _parse_json_or_yaml(loaded)


def _load_yaml(path: Path) -> Dict[str, Tuple[float, float, float]]:
    """Load and normalise a YAML pmt-pattern file."""
    with open(path, "r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    return _parse_json_or_yaml(loaded)


def _load_csv(path: Path) -> Dict[str, Tuple[float, float, float]]:
    """Load a CSV pmt-pattern file with columns pmt_id, x, y [, z]."""
    pattern: Dict[str, Tuple[float, float, float]] = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None or "pmt_id" not in reader.fieldnames:
            raise ValueError("pmt pattern CSV requires a 'pmt_id' column")
        for row in reader:
            x = row.get("x")
            y = row.get("y")
            if x is None or y is None or x == "" or y == "":
                raise ValueError(f"pmt pattern CSV entry missing x/y: {row!r}")
            z = row.get("z")
            pos = [x, y, 0.0 if z in (None, "") else z]
            key, xyz = _parse_entry(row["pmt_id"], pos)
            pattern[key] = xyz
    if not pattern:
        raise ValueError("pmt pattern is empty")
    return pattern


def load_pmt_pattern(path, fmt="auto") -> Dict[str, Tuple[float, float, float]]:
    """Load a pmt-id -> (x, y, z) pattern from a JSON/CSV/YAML file.

    ``fmt`` selects the parser: ``"auto"`` infers it from the file extension,
    or one of ``"json"`` / ``"csv"`` / ``"yaml"``.  Keys are normalised to
    ``str(pmt_id)`` and ``z`` defaults to ``0.0`` when absent.  Raised
    ``ValueError`` for empty/invalid files.
    """
    p = Path(path)
    if not p.exists():
        raise ValueError(f"pmt pattern file not found: {p}")
    if fmt == "auto":
        suffix = p.suffix.lower()
        if suffix == ".json":
            fmt = "json"
        elif suffix == ".csv":
            fmt = "csv"
        elif suffix in (".yaml", ".yml"):
            fmt = "yaml"
        else:
            raise ValueError(f"cannot infer pmt pattern format from {suffix!r}; pass fmt explicitly")
    if fmt == "json":
        return _load_json(p)
    if fmt == "yaml":
        return _load_yaml(p)
    if fmt == "csv":
        return _load_csv(p)
    raise ValueError(f"unsupported pmt pattern format: {fmt!r}")


def cog_reconstruct(charge_per_pmt: Dict[str, float], pattern: Dict[str, Tuple[float, float, float]]) -> Tuple[float, float]:
    """Weighted centroid over pmt_ids present in both maps.

    ``x_cog = sum(w*x)/sum(w)``, ``y_cog = sum(w*y)/sum(w)`` using only ids
    whose charge weight is non-zero and whose position exists in ``pattern``.
    Raises ``ValueError`` when there is no usable charge.
    """
    total_w = 0.0
    x_num = 0.0
    y_num = 0.0
    for pmt_id, w in charge_per_pmt.items():
        if w == 0 or pmt_id not in pattern:
            continue
        pos = pattern[pmt_id]
        x, y = pos[0], pos[1]
        total_w += float(w)
        x_num += float(w) * x
        y_num += float(w) * y
    if total_w == 0:
        raise ValueError("no usable charge for COG reconstruction")
    return x_num / total_w, y_num / total_w


def cog_reconstruct_peak(features: PeakFeatures, runinfo, pattern, config):
    """Return ``(x_cog, y_cog)`` for a peak, or None when charge is empty."""
    if not features.charge_per_pmt:
        return None
    return cog_reconstruct(features.charge_per_pmt, pattern)
