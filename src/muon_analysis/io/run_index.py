"""Run id resolution: accept plain lists, glob patterns or an external file."""

from __future__ import annotations

import glob as _glob
from pathlib import Path
from typing import Iterable, List, Union


def _expand(entry: str) -> List[str]:
    if any(ch in entry for ch in "*?["):
        return sorted(_glob.glob(entry))
    return [entry]


def resolve_run_ids(
    run_ids: Iterable[Union[int, str]],
    runinfo_list_file: str | Path | None = None,
) -> List[str]:
    """Return a de-duplicated, ordered list of run_id strings.

    Each item in ``run_ids`` may be a plain run id (``00179`` / ``179``) or a
    glob pattern (``00*``).  When ``runinfo_list_file`` is given, additional
    run ids are read from that text file (one id/pattern per line).
    """
    result: List[str] = []
    seen: set = set()

    def _add(base: Iterable) -> None:
        for entry in base:
            text = str(entry).strip()
            if not text:
                continue
            for expanded in _expand(text):
                if expanded not in seen:
                    seen.add(expanded)
                    result.append(expanded)

    _add(run_ids)

    if runinfo_list_file is not None:
        with open(runinfo_list_file, "r", encoding="utf-8") as f:
            _add((line.strip() for line in f if line.strip()))

    return result
