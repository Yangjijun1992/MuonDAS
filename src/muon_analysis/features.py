"""Waveform feature computation and integration-window strategy.

Charge (area) integration strategy:
  - ``FixedWindowResolver``: integrate over a fixed / given ``[start, end)``
    range (aligned with the reference ``compute_integral_pe``).
  - ``PeakFinderWindowResolver``: reserved plug-in point — a peak-finding
    algorithm (to be supplied later by the user) determines the waveform
    starting point, from which the integration range is derived.

Both implement :class:`IntegrationWindowResolver` so downstream callers are
agnostic to the chosen strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from muon_analysis.filtering import SignalAccessor
from muon_analysis.models import Peak, PeakFeatures
from muon_analysis.plotting.waveforms import apply_lowpass_filter


class IntegrationWindowResolver(ABC):
    """Resolve the integration range ``(start, end)`` for a waveform."""

    @abstractmethod
    def resolve(self, waveform: np.ndarray, **kwargs) -> Tuple[int, int]:
        """Return ``(start, end)`` indices for the integration window."""
        raise NotImplementedError


@dataclass
class FixedWindowResolver(IntegrationWindowResolver):
    """Fixed / given integration window ``[start, end)``."""

    start: int
    end: int

    def resolve(self, waveform: np.ndarray, **kwargs) -> Tuple[int, int]:
        n = waveform.shape[-1]
        end = min(int(self.end), n)
        start = min(int(self.start), end)
        return start, end


class PeakFinderWindowResolver(IntegrationWindowResolver):
    """Reserved plug-in for peak-finding based integration start.

    TODO: user will supply a peak/signal-start finding algorithm.  Currently
    it falls back to a fixed window so the pipeline remains runnable.
    """

    def __init__(self, fallback: FixedWindowResolver, peak_finder=None):
        self.fallback = fallback
        self.peak_finder = peak_finder

    def resolve(self, waveform: np.ndarray, **kwargs) -> Tuple[int, int]:
        if self.peak_finder is not None:
            start = int(self.peak_finder(waveform, **kwargs))
            _, end = self.fallback.resolve(waveform, **kwargs)
            return start, end
        return self.fallback.resolve(waveform, **kwargs)


def build_window_resolver(config: Dict[str, Any]) -> IntegrationWindowResolver:
    """Construct the configured integration window resolver."""
    features_cfg = config.get("features", {})
    mode = features_cfg.get("integral_window_mode", "fixed")
    start = int(features_cfg.get("integral_start", 20))
    end = int(features_cfg.get("integral_end", 100))
    fixed = FixedWindowResolver(start=start, end=end)
    if mode == "peak_finder":
        return PeakFinderWindowResolver(fallback=fixed)
    return fixed


def integrate_area(
    waveform: np.ndarray,
    resolver: IntegrationWindowResolver,
    signal_polarity: str = "positive",
    baseline: Optional[float] = None,
) -> float:
    """Integrate ``waveform`` over the window resolved by ``resolver``.

    Positive pulses are summed as-is; negative pulses are summed in absolute
    value (aligned with the reference behaviour).
    """
    if baseline is not None:
        waveform = waveform - baseline
    start, end = resolver.resolve(np.asarray(waveform))
    if signal_polarity == "negative":
        return float(np.sum(np.abs(waveform[start:end])))
    return float(np.sum(waveform[start:end]))


def compute_baseline(waveform: np.ndarray, baseline_samples: int = 10) -> float:
    """Mean of the first ``baseline_samples`` samples."""
    return float(np.mean(waveform[:baseline_samples]))


@dataclass
class Features:
    """Feature vector for a single waveform."""

    height: float
    charge: float
    rise_time: float
    width: float
    baseline: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "height": self.height,
            "charge": self.charge,
            "rise_time": self.rise_time,
            "width": self.width,
            "baseline": self.baseline,
        }


def _crossing(waveform: np.ndarray, frac: float, peak_index: int, baseline: float,
              peak_amp: float, direction: int) -> Optional[float]:
    """Find index where amplitude crosses ``frac`` of peak on path to peak."""
    target = baseline + direction * frac * abs(peak_amp - baseline)
    indices = np.arange(len(waveform))
    if direction > 0:
        seg = indices[: peak_index + 1]
    else:
        seg = indices[peak_index:]
    if len(seg) < 2:
        return None
    vals = waveform[seg]
    cross = np.argwhere((vals - target) * direction >= 0)
    if len(cross) == 0:
        return None
    return int(seg[cross[0][0]])

def _fwhm_samples(waveform: np.ndarray, peak_index: int, baseline: float,
                  peak_amp: float, direction: int) -> Optional[float]:
    """Number of samples above the half-maximum level (FWHM in samples)."""
    above = (waveform - baseline) * direction >= 0.5 * abs(peak_amp - baseline)
    if not np.any(above):
        return None
    return float(np.count_nonzero(above))


def compute_features(
    waveform: np.ndarray,
    signal_polarity: str = "positive",
    baseline_samples: int = 10,
    rise_low: float = 0.1,
    rise_high: float = 0.9,
    window: Optional[Tuple[int, int]] = None,
) -> tuple:
    """Compute height, charge, rise_time, width, baseline for a waveform.

    Returns a tuple ``(features: Features, peak_index: int)``.
    """
    wf = np.asarray(waveform, dtype=float)
    baseline = compute_baseline(wf, baseline_samples)
    direction = 1 if signal_polarity == "positive" else -1
    centred = (wf - baseline) * direction
    peak_index = int(np.argmax(centred))
    peak_amp = wf[peak_index]

    if window is not None:
        charge = integrate_area(wf, FixedWindowResolver(window[0], window[1]),
                                signal_polarity=signal_polarity)
    else:
        charge = float(np.sum(centred)) if signal_polarity == "positive" else float(np.sum(np.abs(wf - baseline)))

    height = abs(peak_amp - baseline)

    low_idx = _crossing(wf, rise_low, peak_index, baseline, peak_amp, direction)
    high_idx = _crossing(wf, rise_high, peak_index, baseline, peak_amp, direction)
    if low_idx is not None and high_idx is not None and high_idx > low_idx:
        rise_time = float(high_idx - low_idx)
    else:
        rise_time = float("nan")

    width = _fwhm_samples(wf, peak_index, baseline, peak_amp, direction)
    if width is None:
        width = float("nan")

    feats = Features(
        height=float(height),
        charge=float(charge),
        rise_time=rise_time,
        width=width,
        baseline=baseline,
    )
    return feats, peak_index


def _feature_records(peak: Peak, side: str):
    """Anode or dynode records of a peak (side in {'anode', 'dynode'})."""
    return peak.anode_records if side == "anode" else peak.dynode_records


def _max_ignore_nan(values: List[float], default: float = 0.0) -> float:
    """Max of ``values`` ignoring NaN entries (``default`` when none finite)."""
    finite = [v for v in values if v == v]
    return float(max(finite)) if finite else default


def compute_peak_features(peak: Peak, run_data, gain_db, config) -> PeakFeatures:
    """Per-record + aggregate features for a peak.

    Anode records are integrated with ``signal_polarity="negative"`` over the
    configured fixed window; dynode records are low-pass filtered (when a
    cutoff is configured), scaled by ``plotting.dynode_scale`` (default 110),
    then integrated with ``signal_polarity="positive"``.  Because the dynode
    waveform is scaled before integration, its area (and height) are implicitly
    ``×dynode_scale``.

    Per-record charge is converted to PE via ``charge_to_pe`` using the
    channel gain.  ``charge_per_pmt`` aggregates charge by PMT on the side
    selected by ``cog.charge_source``.
    """
    from muon_analysis.pe_calibration import charge_to_pe

    features_cfg = config.get("features", {})
    integ_start = int(features_cfg.get("integral_start", 20))
    integ_end = int(features_cfg.get("integral_end", 100))
    baseline_samples = int(features_cfg.get("baseline_samples", 10))
    rise_low = float(features_cfg.get("rise_time_low", 0.1))
    rise_high = float(features_cfg.get("rise_time_high", 0.9))

    plot_cfg = config.get("plotting", {})
    dynode_scale = float(plot_cfg.get("dynode_scale", 110))
    lp_cutoff = plot_cfg.get("dynode_lp_cutoff_hz")
    if lp_cutoff is not None:
        lp_cutoff = float(lp_cutoff)
    fs = float(plot_cfg.get("fs", 250e6))

    accessor = SignalAccessor.from_run_data(run_data)

    anode_features: Dict[int, Features] = {}
    anode_pe: Dict[int, float] = {}
    for rec in peak.anode_records:
        sig = accessor.signals([rec.record_id]).reshape(-1)
        feats, _ = compute_features(
            sig,
            signal_polarity="negative",
            baseline_samples=baseline_samples,
            rise_low=rise_low,
            rise_high=rise_high,
            window=(integ_start, integ_end),
        )
        anode_features[rec.record_id] = feats
        anode_pe[rec.record_id] = charge_to_pe(
            feats.charge, gain_db.get_gain(rec.channel)
        )

    dynode_features: Dict[int, Features] = {}
    dynode_pe: Dict[int, float] = {}
    for rec in peak.dynode_records:
        sig = accessor.signals([rec.record_id]).reshape(-1)
        if lp_cutoff is not None:
            sig = apply_lowpass_filter(sig, cutoff_hz=lp_cutoff, fs=fs, order=4)
        sig = sig * dynode_scale
        feats, _ = compute_features(
            sig,
            signal_polarity="positive",
            baseline_samples=baseline_samples,
            rise_low=rise_low,
            rise_high=rise_high,
            window=(integ_start, integ_end),
        )
        dynode_features[rec.record_id] = feats
        dynode_pe[rec.record_id] = charge_to_pe(
            feats.charge, gain_db.get_gain(rec.channel)
        )

    anode_area_pe = float(sum(anode_pe.values()))
    dynode_area_pe = float(sum(dynode_pe.values()))

    heights = [f.height for f in anode_features.values()] \
        + [f.height for f in dynode_features.values()]
    widths = [f.width for f in anode_features.values()] \
        + [f.width for f in dynode_features.values()]
    rise_times = [f.rise_time for f in anode_features.values()] \
        + [f.rise_time for f in dynode_features.values()]

    if peak.dynode_records:
        time_ns = min(r.time_ns for r in peak.dynode_records)
    elif peak.anode_records:
        time_ns = min(r.time_ns for r in peak.anode_records)
    else:
        time_ns = peak.start_time_ns

    charge_per_pmt: Dict[str, float] = {}
    charge_source = config.get("cog", {}).get("charge_source", "anode")
    feat_map = anode_features if charge_source == "anode" else dynode_features
    board = 0 if charge_source == "anode" else 1
    by_chan: Dict[int, float] = {}
    for rec in _feature_records(peak, charge_source):
        by_chan[rec.channel] = by_chan.get(rec.channel, 0.0) \
            + feat_map[rec.record_id].charge
    pmt_map = run_data.runinfo.pmt_id_map
    for channel, charge in by_chan.items():
        pmt_id = pmt_map.get((board, channel))
        if pmt_id is not None:
            charge_per_pmt[str(pmt_id)] = charge

    return PeakFeatures(
        peaks_id=peak.peaks_id,
        time_ns=time_ns,
        channels=list(peak.channels),
        anode_record_ids=[r.record_id for r in peak.anode_records],
        dynode_record_ids=[r.record_id for r in peak.dynode_records],
        anode_features=anode_features,
        dynode_features=dynode_features,
        anode_pe=anode_pe,
        dynode_pe=dynode_pe,
        charge_per_pmt=charge_per_pmt,
        anode_area_pe=anode_area_pe,
        dynode_area_pe=dynode_area_pe,
        peak_height=_max_ignore_nan(heights),
        peak_width=_max_ignore_nan(widths),
        peak_rise_time=_max_ignore_nan(rise_times),
    )
