"""Tests for pulse boundary finding (pulsefinding.py)."""

from __future__ import annotations

import numpy as np
import pytest

from muon_analysis.config import build_config
from muon_analysis.models import Peak, PeakRecord
from muon_analysis.pulsefinding import (
    compute_peak_start_end,
    find_pulse_boundaries,
    findpulse_st_ed,
    pulse_finder,
)


def _neg_pulse(n=200, start=40, width=12, amplitude=500.0, noise=0.0,
               baseline=0.0):
    rng = np.random.default_rng(0)
    wf = rng.normal(0, noise, n) + baseline
    g = np.exp(-((np.arange(n) - (start + width)) ** 2) / (2 * width ** 2))
    wf -= amplitude * g
    return wf


def test_findpulse_st_ed_negative_pulse():
    wf = _neg_pulse(start=40, amplitude=500)
    min_idx = int(np.argmin(wf))
    search_range = 8
    st, mi, ed = findpulse_st_ed(wf, 0.0, min_idx, search_range=search_range)
    assert mi == min_idx
    assert st <= mi <= ed
    assert ed - st > 0
    # boundaries stay within the search range around the reference point
    assert st >= max(0, min_idx - search_range)
    assert ed <= min(len(wf), min_idx + search_range)


def test_find_pulse_boundaries_known_pulse():
    wf = _neg_pulse(start=40, width=12, amplitude=500)
    bounds = find_pulse_boundaries(wf, height_threshold=50)
    assert bounds is not None
    st, ed = bounds
    assert st <= 52 <= ed  # pulse centre (start+width=52) inside the window
    assert 0 <= st < ed <= len(wf)
    # boundaries should be near baseline: |wf[st]|, |wf[ed]| < tol (50) + noise
    assert abs(wf[st]) < 60
    assert abs(wf[ed]) < 60


def test_findpulse_st_ed_skips_clipped_plateau():
    # saturated pulse: flatten 20 samples at the minimum (emulates ADC clipping)
    wf = _neg_pulse(start=40, amplitude=500)
    min_idx = int(np.argmin(wf))
    wf[min_idx - 8:min_idx + 12] = wf[min_idx]
    st, mi, ed = findpulse_st_ed(wf, 0.0, min_idx, search_range=25)
    assert mi == min_idx
    assert st < min_idx - 8   # start lands before the clipped plateau
    assert ed > min_idx + 12  # end lands past the plateau (recovery side)
    assert wf[ed] > wf[min_idx]


def test_pulse_finder_negative_only():
    cfg = build_config()
    neg = _neg_pulse(start=40, amplitude=500)
    assert pulse_finder(neg, cfg) is not None
    # a positive pulse (no inversion) must NOT be found by the negative finder
    pos = -neg
    assert pulse_finder(pos, cfg) is None


def test_pulse_finder_below_threshold_returns_none():
    cfg = build_config(overrides={"pulse_finder": {"height_threshold": 1000.0}})
    small = _neg_pulse(start=40, amplitude=200)
    assert pulse_finder(small, cfg) is None


def test_pulse_finder_noise_only_none():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 2, 200)
    cfg = build_config()
    assert pulse_finder(noise, cfg) is None


def _run_data_with_pulses(interval=4.0):
    from types import SimpleNamespace
    from pathlib import Path
    from muon_analysis.io.data import RunData
    from muon_analysis.models import RunInfo

    length = 200
    # anode: negative pulse @ sample 40; dynode: positive pulse @ sample 60
    anode_wf = _neg_pulse(start=40, amplitude=500)
    dynode_wf = -_neg_pulse(start=60, amplitude=300)  # positive-going

    dtype = [("time", "i8"), ("channel", "i4"), ("board", "i4"),
             ("record_id", "i8"), ("event_length", "i4")]
    dyn = np.zeros(1, dtype=dtype)
    ano = np.zeros(1, dtype=dtype)
    dyn["time"], dyn["channel"], dyn["board"], dyn["record_id"] = [1000, 1, 1, 100]
    dyn["event_length"] = length
    ano["time"], ano["channel"], ano["board"], ano["record_id"] = [1004, 1, 0, 200]
    ano["event_length"] = length

    store = {100: dynode_wf, 200: anode_wf}
    data = SimpleNamespace(records=np.concatenate([ano, dyn]), signals=None)
    data.signals = lambda ids: np.stack([store[int(i)] for i in ids])
    ri = RunInfo(run_id="00179", runtype="t", run_dir=Path("/x"),
                 runinfo_path=Path("/x"), raw_dir=Path("/x"))
    return RunData(runinfo=ri, data=data, dynode_records=dyn,
                   anode_records=ano, data_format="test")


def test_compute_peak_start_end_inverts_dynode():
    from muon_analysis.plotting.waveforms import apply_lowpass_filter
    from muon_analysis.pulsefinding import find_pulse_boundaries

    run_data = _run_data_with_pulses()
    peak = Peak(
        peaks_id=0, start_time_ns=5000.0, end_time_ns=5000.0,
        anode_records=[PeakRecord(record_id=200, channel=1, time_ns=1004.0,
                                  is_dynode=False)],
        dynode_records=[PeakRecord(record_id=100, channel=1, time_ns=1000.0,
                                   is_dynode=True)],
        channels=[1],
    )
    cfg = build_config()
    pf_cfg = cfg["pulse_finder"]
    lp_cutoff = cfg["plotting"]["dynode_lp_cutoff_hz"]
    fs = cfg["plotting"]["fs"]

    def core(wf):
        b = find_pulse_boundaries(
            wf,
            baseline_samples=pf_cfg["baseline_samples"],
            baseline_mode=pf_cfg["baseline_mode"],
            height_threshold=pf_cfg["height_threshold"],
            min_recovery_frac=pf_cfg["min_recovery_frac"],
            end_baseline_tol=pf_cfg["end_baseline_tol"],
            end_consecutive=pf_cfg["end_consecutive"],
        )
        assert b is not None
        return b

    anode_st, anode_ed = core(_neg_pulse(start=40, amplitude=500))
    # stored dynode waveform is positive; the function inverts it for the
    # finder.  With the software LP disabled (dynode_lp_cutoff_hz=None, the
    # hardware 25MHz filter covers it), the finder sees the raw negative form:
    dyn_neg = _neg_pulse(start=60, amplitude=300)
    if lp_cutoff is not None:
        dyn_neg = apply_lowpass_filter(dyn_neg, cutoff_hz=lp_cutoff, fs=fs)
    dyn_st, dyn_ed = core(dyn_neg)
    expected_start = min(1004.0 + anode_st * 4.0, 1000.0 + dyn_st * 4.0)
    expected_end = max(1004.0 + anode_ed * 4.0, 1000.0 + dyn_ed * 4.0)

    compute_peak_start_end([peak], run_data, cfg)
    assert peak.start_time_ns == pytest.approx(expected_start)
    assert peak.end_time_ns == pytest.approx(expected_end)
    # both pulse minima lie inside the window
    assert peak.start_time_ns <= 1004.0 + 52 * 4.0 <= peak.end_time_ns
    assert peak.start_time_ns <= 1000.0 + 72 * 4.0 <= peak.end_time_ns
    # window stays bounded well below the 800 ns waveform
    assert peak.end_time_ns - peak.start_time_ns <= 750.0


def test_find_pulse_boundaries_skips_clipped_plateau():
    # saturated pulse: flat plateau at the minimum (emulates ADC clipping)
    wf = _neg_pulse(start=40, amplitude=500)
    min_idx = int(np.argmin(wf))
    wf[min_idx - 8:min_idx + 12] = wf[min_idx]
    bounds = find_pulse_boundaries(wf, height_threshold=50)
    assert bounds is not None
    st, ed = bounds
    assert st < min_idx - 8  # start lands before the clipped plateau
    assert ed > min_idx + 12  # end lands past the plateau (recovery side)
    assert wf[ed] > wf[min_idx]  # end is well above the clipped level


def test_compute_peak_start_end_no_pulse_keeps_window():
    run_data = _run_data_with_pulses()
    peak = Peak(peaks_id=0, start_time_ns=1000.0, end_time_ns=1000.0,
                anode_records=[], dynode_records=[], channels=[])
    cfg = build_config()
    compute_peak_start_end([peak], run_data, cfg)
    assert peak.start_time_ns == 1000.0
    assert peak.end_time_ns == 1000.0
