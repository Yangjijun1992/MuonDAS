"""Run configuration discovery and parsing (runinfo.json).

Aligned with the reference ``examples/runinfo.py``: discovers
``runinfo.json`` under ``<data_root>/<runtype>/<run_id 5-digit>/``, parses it
and builds a :class:`~muon_analysis.models.RunInfo` carrying the real data
path (``raw_dir``) used downstream by the raw data reader.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Sequence, Set

from muon_analysis.models import RunInfo

STANDARD_FIELDS = frozenset({"run_id", "runtype", "outfile_path", "outfile_name"})

VALID_DATATYPES: Set[str] = frozenset({
    "dark rate",
    "spe gain",
    "after pulse",
})

VALID_RUN_TAG = "pmt test"

R8520_RUNTYPE = "run_R8520"

# Fallback search prefixes used when probing for a runtype automatically.
"""
A run_id may live under different ``runtype`` directories at ``data_root``,
e.g. ``run_R8520/<run_id>``, ``run5_Ar/<run_id>``, ``run6_Xe/<run_id>``,
``run7_Xe/<run_id>``.  ``runtype`` scopes the search path.  When unknown it
can be auto-discovered by probing candidate runtype directories.
"""
RUNTYPE_PROBE_PREFIXES = ("run",)


class RunInfoError(Exception):
    """Base exception for runinfo discovery and parsing."""


class RunInfoNotFoundError(RunInfoError):
    """No runinfo.json found for the given run_id."""


class RunInfoParseError(RunInfoError):
    """Failed to parse runinfo.json content."""


class RunInfoValidationError(RunInfoError):
    """runinfo.json failed validation (wrong run_tag / run_comment)."""


def normalize_run_id(run_id: int | str) -> str:
    return str(run_id).zfill(5)


def validate_run_tag(payload: Dict[str, Any]) -> None:
    run_option = payload.get("run_option", {})
    run_tag = run_option.get("run_tag", "")
    if run_tag.strip().lower() != VALID_RUN_TAG:
        raise RunInfoValidationError(
            f"Invalid run_tag '{run_tag}', expected '{VALID_RUN_TAG}'"
        )


def parse_datatypes(payload: Dict[str, Any]) -> List[str]:
    run_option = payload.get("run_option", {})
    run_comment = run_option.get("run_comment", [])
    if not isinstance(run_comment, list):
        run_comment = [run_comment]

    matched: List[str] = []
    for comment in run_comment:
        normalized = re.sub(r"\s+", " ", comment.strip().lower())
        if normalized in VALID_DATATYPES:
            matched.append(comment.strip())
    if not matched:
        raise RunInfoValidationError(
            f"No valid datatype found in run_comment: {run_comment}"
        )
    return matched


def list_runtypes(
    data_root: str | Path = "/mnt/data/TPC",
    candidates: Sequence[str] | None = None,
) -> List[str]:
    """Return runtype directory names under ``data_root``.

    When ``candidates`` is given it is used verbatim (and only existing ones
    returned).  Otherwise runtype dirs are discovered by listing direct
    children of ``data_root`` whose name starts with a known probe prefix
    (e.g. ``run*``).
    """
    root = Path(data_root)
    if candidates:
        return [rt for rt in candidates if (root / rt).is_dir()]
    if not root.is_dir():
        return []
    return sorted(
        d.name for d in root.iterdir()
        if d.is_dir() and any(
            d.name.startswith(p) for p in RUNTYPE_PROBE_PREFIXES
        )
    )


def discover_runtype(
    run_id: int | str,
    data_root: str | Path = "/mnt/data/TPC",
    candidates: Sequence[str] | None = None,
) -> str:
    """Find the runtype whose directory contains ``runinfo.json`` for run_id.

    Raises :class:`RunInfoNotFoundError` if none is found.
    """
    rid = normalize_run_id(run_id)
    root = Path(data_root)
    probe = candidates or list_runtypes(data_root)
    for rt in probe:
        if (root / rt / rid / "runinfo.json").exists():
            return rt
    raise RunInfoNotFoundError(
        f"No runinfo.json found for run_id={rid} under any runtype in {root}"
    )


def discover_runinfo_path(
    run_id: int | str,
    data_root: str | Path = "/mnt/data/TPC",
    runtype: str = R8520_RUNTYPE,
) -> Path:
    rid = normalize_run_id(run_id)
    root = Path(data_root)
    target = root / runtype / rid / "runinfo.json"
    if not target.exists():
        raise RunInfoNotFoundError(
            f"No runinfo.json found for run_id={rid} under {root / runtype}"
        )
    return target


def load_runinfo_json(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise RunInfoParseError(f"Failed to parse JSON: {p}\n  {e}") from e
    except OSError as e:
        raise RunInfoParseError(f"Failed to read file: {p}\n  {e}") from e


def build_runinfo(
    run_id: int | str,
    runinfo_path: Path,
    payload: Dict[str, Any],
    runtype: str = R8520_RUNTYPE,
    strict_validation: bool = False,
) -> RunInfo:
    rid = normalize_run_id(run_id)
    run_dir = runinfo_path.parent
    run_info_section = payload.get("run_info", {})

    outfile_name = run_info_section.get("outfile_name", "")
    outfile_path_raw = run_info_section.get("outfile_path")

    raw_dir_fallback = run_dir / "RAW"
    raw_dir_source = "runinfo.outfile_path"
    if outfile_path_raw:
        raw_dir = Path(outfile_path_raw)
    else:
        raw_dir = raw_dir_fallback
        raw_dir_source = "fallback (run_dir/RAW)"

    extra_metadata: Dict[str, Any] = {}
    for key, value in run_info_section.items():
        if key not in STANDARD_FIELDS:
            extra_metadata[key] = value
    extra_metadata["raw_dir_source"] = raw_dir_source

    for key, value in payload.items():
        if key == "run_info":
            continue
        extra_metadata[key] = value

    # Datatype / run_tag validation is best-effort: general TPC runs (e.g.
    # muon runs under run6_Xe) use free-form tags/comments rather than the
    # old pmt-test vocabulary.  When strict_validation is False a parse
    # failure yields an empty datatype + a warning instead of aborting.
    if strict_validation:
        validate_run_tag(payload)
        datatype = parse_datatypes(payload)
    else:
        try:
            validate_run_tag(payload)
            datatype = parse_datatypes(payload)
        except RunInfoValidationError as e:
            import warnings
            warnings.warn(f"run_id={rid}: non-fatal runinfo validation issue: {e}")
            datatype = []
        extra_metadata["run_comment"] = (
            payload.get("run_option", {}).get("run_comment", [])
        )

    return RunInfo(
        run_id=rid,
        runtype=runtype,
        run_dir=run_dir,
        runinfo_path=runinfo_path,
        raw_dir=raw_dir,
        outfile_name=outfile_name,
        source=str(runinfo_path),
        datatype=datatype,
        metadata=extra_metadata,
    )


def get_runinfo(
    run_id: int | str,
    data_root: str | Path = "/mnt/data/TPC",
    runtype: str | None = None,
    runtype_candidates: Sequence[str] | None = None,
    strict_validation: bool = False,
) -> RunInfo:
    """Build a :class:`RunInfo` for ``run_id``.

    Parameters
    ----------
    run_id:
        The run id (int or str, zero-padded to 5 digits).
    data_root:
        Root directory containing the runtype directories.
    runtype:
        Optional explicit runtype to scope the search
        (e.g. ``run6_Xe``).  When ``None``, runtype is auto-discovered by
        probing candidate runtype directories under ``data_root``.
    runtype_candidates:
        Optional restricted list of runtype names to probe (e.g. from config),
        used only when ``runtype`` is ``None``.
    strict_validation:
        When True, a missing/mismatched run_tag or datatype raises.  When
        False (default) such issues are downgraded to warnings and yield an
        empty datatype, so general TPC/muon runs can still be loaded.
    """
    if runtype is not None:
        path = discover_runinfo_path(run_id, data_root, runtype)
    else:
        rt = discover_runtype(run_id, data_root, runtype_candidates)
        path = discover_runinfo_path(run_id, data_root, rt)
        runtype = rt

    payload = load_runinfo_json(path)

    # run_info.runtype is authoritative when present.
    payload_runtype = payload.get("run_info", {}).get("runtype")
    if payload_runtype:
        runtype = payload_runtype

    return build_runinfo(
        run_id, path, payload, runtype, strict_validation=strict_validation
    )
