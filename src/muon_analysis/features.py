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

SUMMED_REF = 50  # alignment reference: samples of pre-pulse baseline kept in the sum

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
    width_90area: float = 0.0
    width_50area: float = 0.0

    def as_dict(self) -> Dict[str, float]:
        return {
            "height": self.height,
            "charge": self.charge,
            "rise_time": self.rise_time,
            "width": self.width,
            "baseline": self.baseline,
            "width_90area": self.width_90area,
            "width_50area": self.width_50area,
        }


def width_to_fraction_area(
    waveform: np.ndarray,
    baseline: float,
    start: int,
    end: int,
    frac: float = 0.9,
) -> float:
    """Width (in samples) from ``start`` until ``frac`` of the pulse area is
    accumulated.

    ``width_90area`` algorithm (single waveform):
      1. ``processed = waveform - baseline``;
      2. ``total = sum(|processed[start:end]|)``  (pulse region area);
      3. walk ``k`` from ``start`` accumulating ``cum = sum(|processed[start:k]|)``;
      4. ``width = (first k with cum >= frac * total) - start``.
    Returns NaN when the region is empty or has zero area.
    """
    if end <= start:
        return float("nan")
    proc = np.asarray(waveform, dtype=float) - baseline
    seg = np.abs(proc[start:end])
    total = float(np.sum(seg))
    if total <= 0:
        return float("nan")
    cum = np.cumsum(seg)
    idx = int(np.searchsorted(cum, frac * total))
    return float(idx)


def _record_width_fraction(sig, baseline, rec, n, frac=0.9) -> float:
    """width_Xarea of one record: accumulate from the pulse start over the
    pulse region [start, end] (end falls back to the record length) until
    ``frac`` of the area is reached."""
    start = rec.pulse_start_sample if rec.pulse_start_sample is not None else 0
    end = rec.pulse_end_sample if rec.pulse_end_sample is not None else n
    return width_to_fraction_area(sig, baseline, start, end, frac=frac)


def compute_peak_summed_waveforms(peak, run_data, config, ref=SUMMED_REF,
                                  dynode_scale=None) -> tuple:
    """Aligned summed waveforms over all channels of a peak.

    ``anode_sum``/``dynode_sum`` are produced by aligning every record's
    waveform at its own pulse start (``pulse_start_sample``) to a common
    reference index ``ref`` (samples before the pulse, keeping the pre-pulse
    baseline) and summing pointwise across channels — the summed height at
    each sample is the total amplitude over all channels.

    The dynode channels are each amplified by ``dynode_scale`` **before**
    summing (per-channel scaling, then aligned sum); when ``dynode_scale`` is
    None it is read from ``config['plotting']['dynode_scale']``.  The raw
    (x1) dynode sum is kept for the un-scaled area.

    Records without a resolved pulse start are skipped.  Returns
    ``(anode_sum, dynode_sum, ref_eff, dynode_sum_raw)``; a side with no
    usable records yields ``None``.
    """
    if dynode_scale is None:
        dynode_scale = float((config or {}).get("plotting", {}).get(
            "dynode_scale", 110.0))
    from muon_analysis.filtering import SignalAccessor

    accessor = SignalAccessor.from_run_data(run_data)

    def side_sum(records, scale=1.0):
        if not records:
            return None
        items = [(r, r.pulse_start_sample,
                  len(accessor.signals([r.record_id]).reshape(-1)))
                 for r in records]
        items = [(r, st, L) for r, st, L in items if st is not None]
        if not items:
            return None
        ref_eff = max(int(ref), max(st for _, st, _ in items))
        total_len = ref_eff + max(L - st for _, st, L in items)
        out = np.zeros(total_len, dtype=float)
        for r, st, L in items:
            wf = np.asarray(accessor.signals([r.record_id]).reshape(-1),
                            dtype=float) * float(scale)
            lo = ref_eff - st
            out[lo: lo + L] += wf
        return out

    anode_sum = side_sum(peak.anode_records)
    # dynode sum: each channel amplified by dynode_scale BEFORE summing;
    # the raw (x1) sum is kept separately for the un-scaled area.
    dyn_raw = side_sum(peak.dynode_records)
    dynode_sum = side_sum(peak.dynode_records, scale=dynode_scale)
    ref_used = int(ref)
    for records in (peak.anode_records, peak.dynode_records):
        for r in records:
            if r.pulse_start_sample is not None:
                ref_used = max(ref_used, int(r.pulse_start_sample))
    return anode_sum, dynode_sum, ref_used, dyn_raw


def pulse_peak_index(
    waveform: np.ndarray,
    signal_polarity: str = "positive",
    baseline_samples: int = 10,
) -> int:
    """Sample index of the pulse extremum: argmax for positive pulses
    (dynode), argmin for negative pulses (anode)."""
    wf = np.asarray(waveform, dtype=float)
    baseline = compute_baseline(wf, baseline_samples)
    centred = wf - baseline
    if signal_polarity == "positive":
        return int(np.argmax(centred))
    return int(np.argmin(centred))


def rise_crossing_indices(
    waveform: np.ndarray,
    signal_polarity: str = "positive",
    baseline_samples: int = 10,
    rise_low: float = 0.1,
    rise_high: float = 0.9,
    start: int = 0,
) -> Tuple[Optional[int], Optional[int]]:
    """Deprecated 10%-90% rise-edge crossings (kept for interface parity).

    The rise time is now defined as ``peak_index - pulse_start``; see
    :func:`pulse_peak_index` and :func:`compute_features`.
    """
    return None, None


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
    rise_start: Optional[int] = None,
) -> tuple:
    """Compute height, charge, rise_time, width, baseline for a waveform.

    ``rise_time`` is the range from the pulse start to the pulse-height
    point (peak): ``peak_index - rise_start``, in samples.  The peak is the
    most positive sample for positive pulses (dynode) and the most negative
    for negative pulses (anode).  When ``rise_start`` is None the rise is
    measured from the waveform start (sample 0).

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

    rise_start_idx = int(rise_start) if rise_start is not None else 0
    rise_time = float(peak_index - rise_start_idx)

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
            rise_start=rec.pulse_start_sample,
        )
        feats.width_90area = _record_width_fraction(sig, feats.baseline, rec, len(sig), 0.9)
        feats.width_50area = _record_width_fraction(sig, feats.baseline, rec, len(sig), 0.5)
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
            rise_start=rec.pulse_start_sample,
        )
        feats.width_90area = _record_width_fraction(sig, feats.baseline, rec, len(sig), 0.9)
        feats.width_50area = _record_width_fraction(sig, feats.baseline, rec, len(sig), 0.5)
        dynode_features[rec.record_id] = feats
        dynode_pe[rec.record_id] = charge_to_pe(
            feats.charge, gain_db.get_gain(rec.channel)
        )

    anode_area_pe = 0.0
    dynode_area_pe = 0.0
    area_ano = 0.0
    area_dyn = 0.0

    dyn_scale = float(config.get("plotting", {}).get("dynode_scale", 110.0))
    peak_sum_a, peak_sum_d, peak_sum_ref, peak_sum_draw = \
        compute_peak_summed_waveforms(peak, run_data, config,
                                      dynode_scale=dyn_scale)

    # --- peak-level parameters from the summed waveforms ---
    # integration interval = [anode_sum start, dynode_sum end] from the sum
    # pulse finder; area_ano/area_dyn are raw (x1) areas, *_area_pe scale to
    # PE with the mean channel gain, *_sum_area integrate the full waveform;
    # height/width/rise_time/width_ns/width_90area/50area come from the sum.
    from muon_analysis.pe_calibration import pe_calibration
    from muon_analysis.pulsefinding import find_sum_pulse_bounds

    bounds = find_sum_pulse_bounds(peak_sum_a, peak_sum_d, config)
    a_st = bounds["anode"][0] if "anode" in bounds else 0
    a_ed = bounds["anode"][1] if "anode" in bounds else (
        len(peak_sum_a) if peak_sum_a is not None else 0)
    # integration end: dynode sum end, else anode sum end, else sums' length
    if "dynode" in bounds:
        d_ed = bounds["dynode"][1]
    elif "anode" in bounds:
        d_ed = a_ed
    else:
        d_ed = (len(peak_sum_d) if peak_sum_d is not None
                else len(peak_sum_a) if peak_sum_a is not None else 0)
    if d_ed <= a_st:
        d_ed = len(peak_sum_a) if peak_sum_a is not None else d_ed

    def mean_gain(records):
        if not records:
            return None
        return float(np.mean([gain_db.get_gain(r.channel) for r in records]))

    def seg_integral(wf, lo, hi, polarity):
        if wf is None:
            return 0.0
        w = np.asarray(wf, dtype=float)
        bl = float(np.mean(w[:baseline_samples]))
        seg = w[max(0, lo):min(len(w), hi)] - bl
        if polarity == "negative":
            return float(np.sum(np.abs(seg)))
        return float(np.sum(seg))

    gain_a = mean_gain(peak.anode_records)
    gain_d = mean_gain(peak.dynode_records)
    cal_a = pe_calibration(gain_a) if gain_a else 0.0
    cal_d = pe_calibration(gain_d) if gain_d else 0.0

    area_ano = seg_integral(peak_sum_a, a_st, d_ed, "negative")
    area_dyn = seg_integral(peak_sum_draw, a_st, d_ed, "positive")
    anode_area_pe = area_ano * cal_a
    dynode_area_pe = area_dyn * cal_d
    anode_sum_area = seg_integral(peak_sum_a, 0, len(peak_sum_a)
                                  if peak_sum_a is not None else 0,
                                  "negative") * cal_a
    dynode_sum_area = seg_integral(peak_sum_d, 0, len(peak_sum_d)
                                   if peak_sum_d is not None else 0,
                                   "positive") * cal_d

    # shape parameters from the summed waveforms (anode reference)
    def sum_feats(wf, polarity):
        if wf is None:
            return None
        f, _ = compute_features(wf, signal_polarity=polarity,
                                baseline_samples=baseline_samples,
                                rise_low=rise_low, rise_high=rise_high,
                                rise_start=peak_sum_ref)
        return f

    sf_a = sum_feats(peak_sum_a, "negative")
    sf_d = sum_feats(peak_sum_d, "positive")
    interval_ns = float(config.get("matching", {}).get("sample_interval_ns", 4.0))
    height = 0.0
    width = 0.0
    rise_time = 0.0
    if sf_a is not None:
        height = max(height, sf_a.height)
        width = sf_a.width * interval_ns
        rise_time = sf_a.rise_time * interval_ns
    if sf_d is not None:
        height = max(height, sf_d.height)
    width_ns = float(max(0, a_ed - a_st)) * interval_ns if a_ed > a_st else 0.0

    width_90area = 0.0
    width_50area = 0.0
    if peak_sum_a is not None and a_ed > a_st:
        w = np.asarray(peak_sum_a, dtype=float)
        bl = float(np.mean(w[:baseline_samples]))
        width_90area = width_to_fraction_area(w, bl, a_st, a_ed, 0.9) * interval_ns
        width_50area = width_to_fraction_area(w, bl, a_st, a_ed, 0.5) * interval_ns

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
        anode_sum=peak_sum_a,
        dynode_sum=peak_sum_d,
        sum_ref=peak_sum_ref,
        anode_sum_area=anode_sum_area,
        dynode_sum_area=dynode_sum_area,
        anode_record_ids=[r.record_id for r in peak.anode_records],
        dynode_record_ids=[r.record_id for r in peak.dynode_records],
        anode_features=anode_features,
        dynode_features=dynode_features,
        anode_pe=anode_pe,
        dynode_pe=dynode_pe,
        charge_per_pmt=charge_per_pmt,
        anode_area_pe=anode_area_pe,
        dynode_area_pe=dynode_area_pe,
        area_ano=area_ano,
        area_dyn=area_dyn,
        height=height,
        width=width,
        rise_time=rise_time,
        width_ns=width_ns,
        width_90area=width_90area,
        width_50area=width_50area,
    )
