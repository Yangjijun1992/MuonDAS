"""PMT SPE gain database access.

Backends (aligned with the reference ``pmtdata`` interface plus optional
alternatives):

  - ``pmtdata`` (preferred): ``pmtdata.PMTDataClient().get_pmt_data()``
    returns a DataFrame with ``run_id``, ``channel_id``, ``gain``, ...
  - ``sqlite``: query a ``gain`` table keyed by ``run_id``/``channel_id``.
  - ``csv``: read a CSV with ``run_id``, ``channel_id``, ``gain`` columns.

All backends expose :meth:`get_gain` and a :attr:`version` for provenance.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from typing import Any, Dict


class GainDBError(Exception):
    """Raised for gain database lookup/loading failures."""


def _content_hash(blob: bytes) -> str:
    return hashlib.sha1(blob).hexdigest()[:12]


class GainDB(ABC):
    """Abstract gain lookup interface."""

    @abstractmethod
    def get_gain(self, channel_id: int) -> float:
        raise NotImplementedError

    @property
    @abstractmethod
    def version(self) -> str:
        """Provenance identifier of the gain database."""
        raise NotImplementedError


class PmtDataGainDB(GainDB):
    """Backend backed by the ``pmtdata`` package (reference behaviour).

    The gain column in pmtdata is ``spe_gain``.  When the exact ``run_id``
    has no gain entries, it falls back to the most recent measurement per
    channel (so general runs without a matching gain run still get a gain).
    """

    def __init__(self, run_id: str, version_extra: str = ""):
        self.run_id = str(run_id)
        self._gain_map: Dict[int, float] = {}
        self._version_salt = version_extra
        self._load()

    def _load(self) -> None:
        try:
            import pmtdata as pmt
            import pandas as pd
        except ImportError as e:
            raise GainDBError(
                "pmtdata package is required for the 'pmtdata' gain backend. "
                f"Original error: {e}"
            ) from e
        with pmt.PMTDataClient() as client:
            df = client.get_pmt_data()
        if "spe_gain" not in df.columns:
            raise GainDBError("pmtdata table missing 'spe_gain' column")
        if "run_id" not in df.columns:
            raise GainDBError("pmtdata table missing 'run_id' column")

        # Exact run match first.
        df_run = df[df["run_id"].astype(str) == self.run_id]
        if df_run.empty:
            # Fallback: latest measurement per channel with a valid gain.
            dropna = df[["channel_id", "spe_gain", "measurement_time"]] \
                .dropna(subset=["spe_gain"])
            if dropna.empty:
                raise GainDBError(
                    f"No gain data for run {self.run_id} and none available "
                    "per-channel in pmtdata"
                )
            key = "measurement_time" if "measurement_time" in dropna.columns \
                else "id"
            dropna = dropna.sort_values(key)
            df_run = dropna.groupby("channel_id", as_index=False).tail(1)

        for _, row in df_run.iterrows():
            g = row["spe_gain"]
            if pd.notna(g) and float(g) > 0:
                self._gain_map[int(row["channel_id"])] = float(g)

        if not self._gain_map:
            raise GainDBError(
                f"No valid (nonzero) gains found for run {self.run_id}"
            )
        self._hash = _content_hash(
            repr(sorted((k, v) for k, v in self._gain_map.items())).encode()
        )

    def get_gain(self, channel_id: int) -> float:
        try:
            return self._gain_map[int(channel_id)]
        except KeyError:
            raise GainDBError(
                f"channel_id {channel_id} has no gain for run {self.run_id}"
            ) from None

    @property
    def version(self) -> str:
        return f"pmtdata:run={self.run_id}:{self._hash}"


class SqliteGainDB(GainDB):
    """Backend reading gain from a SQLite table."""

    table = "gain"

    def __init__(self, path: str, run_id: str | None = None,
                 columns=None):
        self.path = str(path)
        self.run_id = run_id
        self._gain_map: Dict[int, float] = {}
        cols = columns or {"run_id": "run_id", "channel_id": "channel_id",
                           "gain": "gain"}
        self._load(cols)

    def _load(self, cols) -> None:
        import sqlite3
        conn = sqlite3.connect(self.path)
        try:
            cur = conn.cursor()
            query = (
                f"SELECT {cols['channel_id']}, {cols['gain']} "
                f"FROM {self.table}"
            )
            params: list = []
            if self.run_id is not None:
                query += f" WHERE {cols['run_id']} = ?"
                params.append(self.run_id)
            cur.execute(query, params)
            rows = cur.fetchall()
        finally:
            conn.close()
        if not rows:
            raise GainDBError(f"No gain rows found in {self.path} "
                              f"(run_id={self.run_id})")
        self._gain_map = {int(ch): float(g) for ch, g in rows}
        self._hash = _content_hash(
            repr(sorted(self._gain_map.items())).encode()
        )

    def get_gain(self, channel_id: int) -> float:
        try:
            return self._gain_map[int(channel_id)]
        except KeyError:
            raise GainDBError(
                f"channel_id {channel_id} not found for run_id {self.run_id}"
            ) from None

    @property
    def version(self) -> str:
        return f"sqlite:{self.path}:{self._hash}"


class CsvGainDB(GainDB):
    """Backend reading gain from a CSV file."""

    def __init__(self, path: str, run_id: str | None = None):
        self.path = str(path)
        self.run_id = run_id
        self._gain_map: Dict[int, float] = {}
        self._load()

    def _load(self) -> None:
        import csv
        with open(self.path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = [r for r in reader]
        if not rows:
            raise GainDBError(f"No gain rows in CSV {self.path}")
        self._gain_map = {}
        for r in rows:
            if self.run_id is not None and r.get("run_id") != self.run_id:
                continue
            self._gain_map[int(r["channel_id"])] = float(r["gain"])
        if not self._gain_map:
            raise GainDBError(f"No gain rows for run_id={self.run_id} in {self.path}")
        self._hash = _content_hash(
            repr(sorted(self._gain_map.items())).encode()
        )

    def get_gain(self, channel_id: int) -> float:
        try:
            return self._gain_map[int(channel_id)]
        except KeyError:
            raise GainDBError(
                f"channel_id {channel_id} not found for run_id {self.run_id}"
            ) from None

    @property
    def version(self) -> str:
        return f"csv:{self.path}:{self._hash}"


def build_gain_db(config: Dict[str, Any], run_id: str | None = None) -> GainDB:
    """Construct the gain DB backend from configuration.

    ``run_id`` overrides the configured gain run id so the gain map is
    queried for the run actually being analyzed.
    """
    gain_cfg = config.get("gain_db", {})
    backend = gain_cfg.get("backend", "pmtdata")
    rid = run_id or gain_cfg.get("run_id", "00179")
    if backend == "pmtdata":
        return PmtDataGainDB(run_id=rid)
    if backend == "sqlite":
        if not gain_cfg.get("sqlite_path"):
            raise GainDBError("gain_db.sqlite_path is required for sqlite backend")
        return SqliteGainDB(
            path=gain_cfg["sqlite_path"], run_id=rid
        )
    if backend == "csv":
        if not gain_cfg.get("csv_path"):
            raise GainDBError("gain_db.csv_path is required for csv backend")
        return CsvGainDB(path=gain_cfg["csv_path"], run_id=rid)
    raise GainDBError(f"Unsupported gain backend: {backend!r}")
