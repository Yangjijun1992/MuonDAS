"""Candidate rough filtering: noise (asymmetry), length / area, amplitude.

Aligned with the reference notebook:
  - ``asymmetry_calculation`` : reject noise (dynode positive, anode negative);
    keep ``asym > asym_min``.
  - length / segment-area selection (e.g. large muon pulses): keep records
    with ``event_length >= min_event_length`` and ``seg_area_pe >= ...``.
  - amplitude (height) bounds are applied when configured.

Signals are fetched via the records-view ``signals(record_ids)`` accessor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

import numpy as np
import numpy.lib.recfunctions as rfn


from muon_analysis.models import MuonCandidate


@dataclass
class Candidate:
    """A surviving candidate event (matched pair)."""

    anode_idx: int
    dynode_idx: int
    channel: int
    dt_ns: float
    anode_area_pe: float
    dynode_area_pe: float
    anode_seg_area_pe: float
    dynode_seg_area_pe: float
    event_length: int
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> Dict[str, Any]:
        d = self.metadata.copy()
        d.update({
            "anode_record_id": self.anode_idx,
            "dynode_record_id": self.dynode_idx,
            "channel": self.channel,
            "dt_ns": self.dt_ns,
            "anode_area_pe": self.anode_area_pe,
            "dynode_area_pe": self.dynode_area_pe,
            "anode_seg_area_pe": self.anode_seg_area_pe,
            "dynode_seg_area_pe": self.dynode_seg_area_pe,
            "event_length": self.event_length,
        })
        return d


class SignalAccessor:
    """Fetch waveforms for record ids from a records-view or npy/hdf5 data."""

    def __init__(self, data: Any, records: Any):
        self._data = data
        self._records = records
        # For npy/h5 backends, signals may be stored in a parallel array.
        self._sig_map: Dict[int, np.ndarray] = {}
        if hasattr(data, "signals") and data.signals is not None:
            self._mode = "view"
        else:
            self._mode = "array"

    def signals(self, record_ids) -> np.ndarray:
        ids = np.asarray(record_ids)
        if self._mode == "view":
            out = self._data.signals(ids)
        else:
            out = np.stack([self._sig_map[int(i)] for i in ids])
        return np.atleast_2d(np.asarray(out, dtype=float))

    @classmethod
    def from_run_data(cls, run_data: Any) -> "SignalAccessor":
        return cls(run_data.data, None)


def _signals_from_ids(accessor, ids) -> np.ndarray:
    arr = accessor.signals(ids)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr


def asymmetry_calculation(
    records,
    accessor,
    signal_polarity: str = "positive",
    baseline_samples: int = 10,
    progress: bool = False,
):
    """Compute waveform asymmetry and attach an ``asym`` field.

    ``asym = (peak - baseline) / range`` for positive pulses,
    ``asym = (baseline - valley) / range`` for negative pulses.
    """
    if "asym" in records.dtype.names:
        records = rfn.drop_fields(records, "asym")
    total = len(records)
    asym_results = np.zeros(total, dtype=np.float32)

    ids = records["record_id"]
    signals = _signals_from_ids(accessor, ids)

    baselines = np.mean(signals[:, :baseline_samples], axis=1)
    peaks = np.max(signals, axis=1)
    valleys = np.min(signals, axis=1)
    ranges = peaks - valleys

    with np.errstate(divide="ignore", invalid="ignore"):
        if signal_polarity == "positive":
            batch_asym = (peaks - baselines) / ranges
        else:
            batch_asym = (baselines - valleys) / ranges
        batch_asym = np.nan_to_num(batch_asym, nan=0.0, posinf=0.0, neginf=0.0)
    asym_results[:] = batch_asym

    new_records = rfn.append_fields(
        records, "asym", asym_results, usemask=False
    )
    return new_records


def _area_pe_for(records, accessor, gain_db, polarity: str,
                 config: Dict[str, Any], seg: bool) -> np.ndarray:
    from muon_analysis.pe_calibration import (
        compute_integral_pe,
        compute_raw_segment_pe,
    )
    ids = records["record_id"]
    channels = records["channel"]
    signals = _signals_from_ids(accessor, ids)
    if seg:
        return compute_raw_segment_pe(signals, channels, gain_db, polarity)
    return compute_integral_pe(signals, channels, gain_db, polarity, config)


def _apply_area_pe(records, accessor, gain_db, polarity, config) -> Any:
    area_pe = _area_pe_for(records, accessor, gain_db, polarity, config, seg=False)
    seg_area_pe = _area_pe_for(records, accessor, gain_db, polarity, config, seg=True)
    records = rfn.drop_fields(records, ["area_pe", "seg_area_pe"], usemask=False) \
        if {"area_pe", "seg_area_pe"}.issubset(records.dtype.names) else records
    records = rfn.append_fields(
        records, ["area_pe", "seg_area_pe"], [area_pe, seg_area_pe], usemask=False
    )
    return records


def filter_candidates(
    match_df,
    run_data,
    gain_db,
    config: Dict[str, Any],
) -> List[Candidate]:
    """Filter matched pairs into a list of :class:`Candidate`.

    Steps:
      1. Slice matched anode/dynode records.
      2. Apply noise (asymmetry) filter to both.
      3. Compute & apply length / segment-area selection on anode.
      4. Assemble candidates, re-indexing matched pairs to surviving rows.
    """
    anode_records = run_data.anode_records
    dynode_records = run_data.dynode_records
    accessor = SignalAccessor.from_run_data(run_data)

    filt_cfg = config.get("filtering", {})
    baseline_samples = int(config["features"].get("baseline_samples", 10))
    pos = filt_cfg.get("signal_positive_polarity", {})
    neg = filt_cfg.get("signal_negative_polarity", {})
    asym_dyn_min = pos.get("asym_min", 0.0)
    asym_ano_min = neg.get("asym_min", 0.0)
    min_len = filt_cfg.get("min_event_length", 0)
    min_area = filt_cfg.get("min_seg_area_pe")
    height_ano_min = neg.get("height_min")
    height_ano_max = neg.get("height_max")
    height_dyn_min = pos.get("height_min")
    height_dyn_max = pos.get("height_max")

    anode_idx = match_df["anode_idx"].to_numpy()
    dyn_idx = match_df["dynode_idx"].to_numpy()
    dt = match_df["dt"].to_numpy()

    ano_sel = anode_records[anode_idx]
    dyn_sel = dynode_records[dyn_idx]

    ano_sel = asymmetry_calculation(ano_sel, accessor, "negative", baseline_samples)
    dyn_sel = asymmetry_calculation(dyn_sel, accessor, "positive", baseline_samples)

    mask = (ano_sel["asym"] > asym_ano_min) & (dyn_sel["asym"] > asym_dyn_min)

    ano_f = ano_sel[mask]
    dyn_f = dyn_sel[mask]

    ano_f = _apply_area_pe(ano_f, accessor, gain_db, "negative", config)
    dyn_f = _apply_area_pe(dyn_f, accessor, gain_db, "positive", config)

    sel_mask = np.ones(len(ano_f), dtype=bool)
    if min_len and min_len > 0:
        sel_mask &= ano_f["event_length"] >= min_len
    if min_area is not None:
        sel_mask &= ano_f["seg_area_pe"] >= min_area

    if height_ano_min is not None:
        sel_mask &= _heights(ano_f, accessor) >= height_ano_min
    if height_ano_max is not None:
        sel_mask &= _heights(ano_f, accessor) <= height_ano_max
    if height_dyn_min is not None:
        sel_mask &= _heights(dyn_f, accessor) >= height_dyn_min
    if height_dyn_max is not None:
        sel_mask &= _heights(dyn_f, accessor) <= height_dyn_max

    idx = np.where(sel_mask)[0]
    dt_survive = dt[mask]
    candidates: List[Candidate] = []
    for i in idx:
        candidates.append(Candidate(
            anode_idx=int(ano_f[i]["record_id"]),
            dynode_idx=int(dyn_f[i]["record_id"]),
            channel=int(ano_f[i]["channel"]),
            dt_ns=float(dt_survive[i]),
            anode_area_pe=float(ano_f[i]["area_pe"]),
            dynode_area_pe=float(dyn_f[i]["area_pe"]),
            anode_seg_area_pe=float(ano_f[i]["seg_area_pe"]),
            dynode_seg_area_pe=float(dyn_f[i]["seg_area_pe"]),
            event_length=int(ano_f[i]["event_length"]),
            metadata={"anode_time": float(ano_f[i]["time"]),
                      "dynode_time": float(dyn_f[i]["time"])},
        ))
    return candidates


def _heights(records, accessor) -> np.ndarray:
    signals = _signals_from_ids(accessor, records["record_id"])
    baseline = np.mean(signals[:, :10], axis=1)
    peaks = np.max(signals, axis=1)
    return np.abs(peaks - baseline)


def filter_muon_candidates(peaks, peak_features, config) -> List[MuonCandidate]:
    """Peak-level muon candidate selection.

    All criteria come from ``config["filtering"]``; a ``None``/absent value
    disables that cut.  Surviving peaks are returned as
    :class:`~muon_analysis.models.MuonCandidate` with a
    ``passed_conditions`` map recording each criterion's verdict.

    ``peaks`` and ``peak_features`` are parallel lists matched by ``peaks_id``;
    a ``ValueError`` is raised if a peak has no corresponding
    :class:`~muon_analysis.models.PeakFeatures`.
    """
    filt_cfg = config.get("filtering", {})
    height_min = filt_cfg.get("height_min")
    height_max = filt_cfg.get("height_max")
    width_min = filt_cfg.get("width_min")
    width_max = filt_cfg.get("width_max")
    rise_time_max = filt_cfg.get("rise_time_max")
    min_area_pe_anode = filt_cfg.get("min_area_pe_anode")
    min_area_pe_dynode = filt_cfg.get("min_area_pe_dynode")

    feat_by_id = {pf.peaks_id: pf for pf in peak_features}

    candidates: List[MuonCandidate] = []
    for peak in peaks:
        pf = feat_by_id.get(peak.peaks_id)
        if pf is None:
            raise ValueError(f"no PeakFeatures for peaks_id={peak.peaks_id}")

        conditions = {
            "height_min": height_min is None or pf.height >= height_min,
            "height_max": height_max is None or pf.height <= height_max,
            "width_min": width_min is None or pf.width >= width_min,
            "width_max": width_max is None or pf.width <= width_max,
            "rise_time_max": rise_time_max is None
            or pf.rise_time <= rise_time_max,
            "min_area_pe_anode": min_area_pe_anode is None
            or pf.anode_area_pe >= min_area_pe_anode,
            "min_area_pe_dynode": min_area_pe_dynode is None
            or pf.dynode_area_pe >= min_area_pe_dynode,
        }
        if all(conditions.values()):
            candidates.append(MuonCandidate(
                peaks_id=peak.peaks_id,
                features=pf,
                start_time_ns=peak.start_time_ns,
                end_time_ns=peak.end_time_ns,
                passed_conditions=conditions,
            ))
    return candidates
