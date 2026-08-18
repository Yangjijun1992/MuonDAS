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
    waveform: np.ndarray,
    baseline_samples: int = 30,
    mode: str = "global_median",
) -> Tuple[np.ndarray, float]:
    """Subtract a robust baseline; return ``(processed, baseline)``.

    ``mode``:
      - ``"global_median"`` (default): median of the whole waveform.  Robust
        when the pulse starts early in the record (the reference first-N mean
        is corrupted when the first ``baseline_samples`` contain the pulse
        edge, which shifts the whole post-pulse tail away from zero).
      - ``"first_mean"``: reference behaviour, mean of the first
        ``baseline_samples``.
    """
    wf = np.asarray(waveform, dtype=float)
    if mode == "first_mean":
        n = min(int(baseline_samples), len(wf))
        baseline = float(np.mean(wf[:n]))
    else:
        baseline = float(np.median(wf))
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

    # skip a clipped (saturated) flat plateau at the minimum, then walk to the
    # true pulse start/end; without this the monotonic walk stalls inside the
    # plateau and both boundaries land on the clipped region
    start_index = min_index
    while start_index > start_range and wf[start_index] == wf[min_index]:
        start_index -= 1
    while start_index > start_range and wf[start_index] < wf[start_index - 1]:
        start_index -= 1

    end_index = min_index
    while end_index + 1 < end_range and wf[end_index + 1] == wf[min_index]:
        end_index += 1
    while end_index + 1 < end_range and wf[end_index + 1] > wf[end_index]:
        end_index += 1

    return start_index, min_index, end_index


def find_pulse_boundaries(
    waveform: np.ndarray,
    baseline_samples: int = 30,
    baseline_mode: str = "global_median",
    height_threshold: float = 10.0,
    min_recovery_frac: float = 0.3,
    end_baseline_tol: float = 20.0,
    end_consecutive: int = 3,
) -> Optional[Tuple[int, int]]:
    """Full main-pulse ``(start, end)`` for a negative-going waveform.

    Baseline-subtract -> argmin -> height check -> walk to the pulse
    boundaries:

      - a **robust baseline** (``baseline_mode``) is used so the pulse edge
        inside the first samples does not shift the tail away from zero;
      - the **clipped (saturated) flat plateau** at the minimum is skipped
        first, so the boundaries do not stall inside it;
      - LEFT: walk while the signal is still descending (pulse start edge);
      - RIGHT: the end must **return to the baseline** and stay there — the
        end sample plus the following ``end_consecutive`` samples must all lie
        within ``end_baseline_tol`` ADC of the baseline (a transient
        oscillation dip is not accepted as the end); if no stable baseline
        return exists within the record, the end falls back to the record end;
      - a pulse is accepted only when the recovery rise is a meaningful
        fraction (``min_recovery_frac``) of the pulse height, which rejects
        spurious minima (e.g. an un-inverted positive pulse).

    Returns ``(start, end)`` sample indices or None when no pulse is found.
    """
    processed, _ = preprocess_waveform(waveform, baseline_samples, baseline_mode)
    min_idx = int(np.argmin(processed))
    height = abs(float(processed[min_idx]))
    if height < float(height_threshold):
        return None

    start_idx = min_idx
    while start_idx > 0 and processed[start_idx] == processed[min_idx]:
        start_idx -= 1
    while start_idx > 0 and processed[start_idx] <= processed[start_idx - 1]:
        start_idx -= 1

    end_idx = min_idx
    n = len(processed)
    while end_idx + 1 < n and processed[end_idx + 1] == processed[min_idx]:
        end_idx += 1
    # end must return to baseline AND stay there: the end sample plus the
    # following ``end_consecutive`` samples must all be within tol of the
    # baseline, so a transient oscillation dip is not mistaken for the end.
    required = 1 + int(end_consecutive)
    count = 0
    found = None
    for i in range(end_idx, n):
        if abs(processed[i]) < float(end_baseline_tol):
            count += 1
            if count >= required:
                found = i - required + 1
                break
        else:
            count = 0
    end_idx = found if found is not None else n - 1

    rise = float(processed[end_idx] - processed[min_idx])
    if rise < float(min_recovery_frac) * height:
        return None
    return start_idx, end_idx


def pulse_finder(
    waveform: np.ndarray,
    config: Optional[Dict[str, Any]] = None,
    end_consecutive: Optional[int] = None,
) -> Optional[Tuple[int, int]]:
    """Pluggable pulse-boundary finder (negative-going pulse required).

    Borrows the ``findpulse_st_ed`` / main-pulse walking from the reference
    ``pmt_analysis`` repo, extended to skip clipped (saturated) plateaus and
    to end the pulse at its baseline return.  Dynode waveforms (positive)
    must be inverted by the caller.  Returns ``(pulse_start, pulse_end)``
    sample indices, or None when no pulse is found.  ``end_consecutive``
    overrides the config value: the number of near-baseline samples after the
    end that must stay within tolerance (0 = end at the first baseline return;
    the anode uses 0, the dynode uses the configured confirmation).  Thresholds
    come from ``config['pulse_finder']`` (see config.py).
    """
    cfg = (config or {}).get("pulse_finder") or {}
    ec = cfg.get("end_consecutive", 3) if end_consecutive is None else end_consecutive
    return find_pulse_boundaries(
        waveform,
        baseline_samples=cfg.get("baseline_samples", 30),
        baseline_mode=cfg.get("baseline_mode", "global_median"),
        height_threshold=cfg.get("height_threshold", 10.0),
        min_recovery_frac=cfg.get("min_recovery_frac", 0.3),
        end_baseline_tol=cfg.get("end_baseline_tol", 20.0),
        end_consecutive=ec,
    )


def compute_peak_start_end(peaks, run_data, config) -> None:
    """Recompute peak start/end from per-channel pulse boundaries (in place).

    Clustering (100 ns record-time window) is unchanged; this only refines the
    peak start/end.  For each peak, **every** anode record (negative pulse,
    raw waveform) and **every** dynode record (low-pass filtered per
    ``plotting.dynode_lp_cutoff_hz`` — matching the verification plots — then
    inverted, positive -> negative) is fed to :func:`pulse_finder`; each
    record's own boundaries are stored on
    ``PeakRecord.pulse_start_sample`` / ``pulse_end_sample``.

    ``peak.start`` = min over all records' pulse starts, ``peak.end`` = max
    over all records' pulse ends.  Records whose end fell back to the record
    end (no stable baseline return found) do **not** contribute to the
    aggregate window, so a ringing channel without a proper end cannot widen
    the peak window.
    """
    from muon_analysis.filtering import SignalAccessor
    from muon_analysis.plotting.waveforms import apply_lowpass_filter

    interval = float(config.get("matching", {}).get("sample_interval_ns", 4.0))
    end_consecutive = int(config.get("pulse_finder", {}).get(
        "end_consecutive", 3))
    plot_cfg = config.get("plotting", {})
    lp_cutoff = plot_cfg.get("dynode_lp_cutoff_hz")
    if lp_cutoff is not None:
        lp_cutoff = float(lp_cutoff)
    fs = float(plot_cfg.get("fs", 250e6))
    accessor = SignalAccessor.from_run_data(run_data)

    for peak in peaks:
        starts: List[float] = []
        ends: List[float] = []
        for rec in peak.anode_records:
            wf = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                            dtype=float)
            # anode end: from the peak walking right to the FIRST baseline
            # return (no stability confirmation)
            bounds = pulse_finder(wf, config, end_consecutive=0)
            if bounds is not None:
                rec.pulse_start_sample, rec.pulse_end_sample = bounds
                if bounds[1] < len(wf) - end_consecutive:
                    starts.append(rec.time_ns + bounds[0] * interval)
                    ends.append(rec.time_ns + bounds[1] * interval)
        for rec in peak.dynode_records:
            wf = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                            dtype=float)
            if lp_cutoff is not None:
                wf = apply_lowpass_filter(wf, cutoff_hz=lp_cutoff, fs=fs)
            # dynode end: baseline return confirmed by end_consecutive samples
            bounds = pulse_finder(-wf, config)
            if bounds is not None:
                rec.pulse_start_sample, rec.pulse_end_sample = bounds
                if bounds[1] < len(wf) - end_consecutive:
                    starts.append(rec.time_ns + bounds[0] * interval)
                    ends.append(rec.time_ns + bounds[1] * interval)
        if starts and ends:
            peak.start_time_ns = float(min(starts))
            peak.end_time_ns = float(max(ends))
