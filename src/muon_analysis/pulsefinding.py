"""Pulse boundary finding (寻峰) for negative-going pulses.

Borrows the main-pulse algorithm from the reference ``pmt_analysis`` repo
(``findpulse_st_ed`` / ``find_main_pulses_per_channel`` in
``src/pmt_analysis/analysis/app.py``): baseline subtraction -> argmin ->
left/right boundary walk.

The finder assumes a **negative pulse** (minimum).  Dynode waveforms are
positive-going and must be **inverted** by the caller before searching.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def preprocess_waveform(
    waveform: np.ndarray, baseline_samples: int = 30
) -> Tuple[np.ndarray, float]:
    """Subtract the baseline (mean of the first ``baseline_samples``)."""
    n = min(int(baseline_samples), len(waveform))
    wf = np.asarray(waveform, dtype=float)
    baseline = float(np.mean(wf[:n]))
    return wf - baseline, baseline


def findpulse_st_ed(
    waveform: np.ndarray,
    baseline: float,
    reference_point: int,
    search_range: int = 5,
) -> Tuple[int, int, int]:
    """Reference-point pulse boundary finder (negative pulse).

    Port of ``pmt_analysis`` ``findpulse_st_ed``: local minimum within
    ``search_range`` of ``reference_point``, then walk left/right to the
    pulse boundaries.  Returns ``(start_index, min_index, end_index)``.

    Parameters
    ----------
    waveform:
        Baseline-subtracted (or raw) 1-D array with a negative-going pulse.
    baseline:
        Baseline offset (informational; kept for interface parity).
    reference_point:
        Approximate pulse position (e.g. the argmin of a processed waveform).
    search_range:
        Max samples to walk each direction from the reference point.
    """
    wf = np.asarray(waveform, dtype=float)
    start_range = max(0, int(reference_point) - search_range)
    end_range = min(len(wf), int(reference_point) + search_range)

    min_index = int(reference_point)
    min_value = wf[min_index]
    for i in range(start_range, end_range):
        if wf[i] < min_value:
            min_value = wf[i]
            min_index = i

    start_index = min_index
    while start_index > start_range and wf[start_index] < wf[start_index - 1]:
        start_index -= 1

    end_index = min_index
    if end_index + 1 < end_range and wf[min_index] == wf[end_index + 1]:
        end_index += 1
    while end_index + 1 < end_range and wf[end_index + 1] > wf[end_index]:
        end_index += 1

    return start_index, min_index, end_index


def find_pulse_boundaries(
    waveform: np.ndarray,
    baseline_samples: int = 30,
    height_threshold: float = 50.0,
    end_baseline_tol: float = 50.0,
    end_consecutive: int = 3,
) -> Optional[Tuple[int, int]]:
    """Full main-pulse ``(start, end)`` for a negative-going waveform.

    Baseline-subtract -> argmin -> height check -> walk left to the pulse
    start -> walk right until ``end_consecutive`` consecutive samples return
    within ``end_baseline_tol`` ADC of the baseline.  Returns None when the
    pulse height is below ``height_threshold``.
    """
    processed, _ = preprocess_waveform(waveform, baseline_samples)
    min_idx = int(np.argmin(processed))
    height = abs(float(processed[min_idx]))
    if height < float(height_threshold):
        return None

    start_idx = min_idx
    while start_idx > 0 and processed[start_idx] <= processed[start_idx - 1]:
        start_idx -= 1

    end_idx = min_idx
    count = 0
    while end_idx < len(processed) - 1:
        end_idx += 1
        if abs(processed[end_idx]) < float(end_baseline_tol):
            count += 1
            if count >= int(end_consecutive):
                break
        else:
            count = 0

    return start_idx, end_idx


def pulse_finder(
    waveform: np.ndarray, config: Optional[Dict[str, Any]] = None
) -> Optional[Tuple[int, int]]:
    """Pluggable pulse-boundary finder (negative-going pulse required).

    Borrows ``findpulse_st_ed``: baseline-subtract -> argmin as reference ->
    bounded walk (``search_range``) to the pulse-core start/end.  Dynode
    waveforms (positive) must be inverted by the caller.  Returns
    ``(pulse_start, pulse_end)`` sample indices, or None when no pulse is
    found.  Thresholds come from ``config['pulse_finder']`` (see config.py).
    """
    cfg = (config or {}).get("pulse_finder") or {}
    baseline_samples = int(cfg.get("baseline_samples", 30))
    height_threshold = float(cfg.get("height_threshold", 50.0))
    search_range = int(cfg.get("search_range", 5))

    processed, _ = preprocess_waveform(waveform, baseline_samples)
    min_idx = int(np.argmin(processed))
    if abs(processed[min_idx]) < height_threshold:
        return None
    start, _, end = findpulse_st_ed(processed, 0.0, min_idx,
                                    search_range=search_range)
    return start, end


def compute_peak_start_end(peaks, run_data, config) -> None:
    """Recompute peak start/end from per-channel pulse boundaries (in place).

    For each peak, every anode record (negative pulse) and every dynode record
    (**inverted first**, positive -> negative) is fed to :func:`pulse_finder`;
    sample boundaries are converted to absolute time via
    ``record.time_ns + sample * sample_interval_ns``.  ``peak.start`` = min
    over all channels' pulse starts, ``peak.end`` = max over all channels'
    pulse ends.  Records with no pulse (below threshold) are skipped.
    """
    from muon_analysis.filtering import SignalAccessor

    interval = float(config.get("matching", {}).get("sample_interval_ns", 4.0))
    accessor = SignalAccessor.from_run_data(run_data)

    for peak in peaks:
        starts: List[float] = []
        ends: List[float] = []
        for rec in peak.anode_records:
            wf = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                            dtype=float)
            bounds = pulse_finder(wf, config)
            if bounds is not None:
                starts.append(rec.time_ns + bounds[0] * interval)
                ends.append(rec.time_ns + bounds[1] * interval)
        for rec in peak.dynode_records:
            wf = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                            dtype=float)
            bounds = pulse_finder(-wf, config)
            if bounds is not None:
                starts.append(rec.time_ns + bounds[0] * interval)
                ends.append(rec.time_ns + bounds[1] * interval)
        if starts and ends:
            peak.start_time_ns = float(min(starts))
            peak.end_time_ns = float(max(ends))
