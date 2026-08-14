"""Unit tests for peak-level verification plots (plan module 5, pre-filter)."""

from __future__ import annotations

from muon_analysis.models import Peak, PeakRecord
from muon_analysis.plotting.waveforms import (
    plot_peak_overlay,
    plot_peak_pairs,
    plot_peak_verification,
)
from conftest import build_synthetic_run_data


def _peak():
    recs = []
    for ch in (0, 1):
        recs.append(PeakRecord(record_id=2000 + ch, channel=ch,
                               time_ns=100.0, is_dynode=False))
        recs.append(PeakRecord(record_id=1000 + ch, channel=ch,
                               time_ns=100.0, is_dynode=True))
    return Peak(peaks_id=7, start_time_ns=100.0, end_time_ns=200.0,
                anode_records=[r for r in recs if not r.is_dynode],
                dynode_records=[r for r in recs if r.is_dynode],
                channels=[0, 1])


def test_plot_peak_verification(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    saved = plot_peak_verification(_peak(), run_data, tmp_path, "00179",
                                   plot_len=100)
    assert len(saved) == 3
    for p in saved:
        assert p.exists()
    names = [p.name for p in saved]
    assert any("verify_anode" in n for n in names)
    assert any("verify_dynode" in n for n in names)
    assert any("verify_compare" in n for n in names)


def test_plot_peak_verification_empty_records(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    from muon_analysis.models import Peak
    empty = Peak(peaks_id=8, start_time_ns=0.0, end_time_ns=1.0)
    assert plot_peak_verification(empty, run_data, tmp_path, "00179") == []


def _small_peak():
    """A small peak with 2 anode + 2 dynode records on channels 0,1."""
    return Peak(
        peaks_id=7,
        start_time_ns=5000.0,
        end_time_ns=5900.0,
        anode_records=[
            PeakRecord(record_id=2000, channel=0, time_ns=5006.0, is_dynode=False),
            PeakRecord(record_id=2001, channel=1, time_ns=5010.0, is_dynode=False),
        ],
        dynode_records=[
            PeakRecord(record_id=1000, channel=0, time_ns=5000.0, is_dynode=True),
            PeakRecord(record_id=1001, channel=1, time_ns=5004.0, is_dynode=True),
        ],
        channels=[0, 1],
    )


def test_plot_peak_pairs(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    paths = plot_peak_pairs(_small_peak(), run_data, tmp_path, "00179")
    assert len(paths) == 1
    assert paths[0].exists()


def test_plot_peak_overlay(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    paths = plot_peak_overlay(_small_peak(), run_data, tmp_path, "00179")
    assert len(paths) == 1
    assert paths[0].exists()


def test_plot_peak_pairs_empty_returns_empty(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    peak = Peak(peaks_id=1, start_time_ns=0.0, end_time_ns=100.0)
    assert plot_peak_pairs(peak, run_data, tmp_path, "00179") == []


def test_plot_peak_overlay_empty_returns_empty(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    peak = Peak(peaks_id=1, start_time_ns=0.0, end_time_ns=100.0)
    assert plot_peak_overlay(peak, run_data, tmp_path, "00179") == []


def test_plot_peak_pairs_filters(tmp_path):
    """Exercise the low-pass filter path (lp_cutoff_hz given)."""
    run_data, _, _ = build_synthetic_run_data()
    paths = plot_peak_pairs(
        _small_peak(), run_data, tmp_path, "00179", lp_cutoff_hz=45e6
    )
    assert len(paths) == 1
    assert paths[0].exists()


def test_plot_peak_overlay_filters(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    paths = plot_peak_overlay(
        _small_peak(), run_data, tmp_path, "00179", lp_cutoff_hz=45e6
    )
    assert len(paths) == 1
    assert paths[0].exists()


def test_plot_peak_overlay_short_waveform(tmp_path):
    """Truncate, do not pad, when waveform is shorter than plot_len."""
    run_data, _, _ = build_synthetic_run_data()
    peak = Peak(
        peaks_id=2,
        start_time_ns=0.0,
        end_time_ns=100.0,
        anode_records=[PeakRecord(record_id=2000, channel=0, time_ns=6.0, is_dynode=False)],
        dynode_records=[PeakRecord(record_id=1000, channel=0, time_ns=0.0, is_dynode=True)],
        channels=[0],
    )
    paths = plot_peak_pairs(peak, run_data, tmp_path, "00179", plot_len=500)
    assert len(paths) == 1
    assert paths[0].exists()
