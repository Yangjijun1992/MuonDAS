"""Tests for muon_analysis.clustering.cluster_peaks."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from muon_analysis.clustering import cluster_peaks
from muon_analysis.config import build_config
from muon_analysis.matching import match_events
from muon_analysis.io.data import RunData
from muon_analysis.models import RunInfo

from conftest import build_synthetic_run_data

_REC_DTYPE = [("time", "i8"), ("channel", "i4"), ("board", "i4"),
              ("record_id", "i8"), ("event_length", "i4")]


def _make_run_data(dyn_times, ano_times, dyn_ch, ano_ch):
    """Build a minimal RunData with one dynode+anode pair per entry."""
    n = len(dyn_times)
    dyn = np.zeros(n, dtype=_REC_DTYPE)
    ano = np.zeros(n, dtype=_REC_DTYPE)
    for i in range(n):
        dyn["time"][i] = int(dyn_times[i])
        dyn["channel"][i] = dyn_ch[i]
        dyn["board"][i] = 1
        dyn["record_id"][i] = 1000 + i
        dyn["event_length"][i] = 200
        ano["time"][i] = int(ano_times[i])
        ano["channel"][i] = ano_ch[i]
        ano["board"][i] = 0
        ano["record_id"][i] = 2000 + i
        ano["event_length"][i] = 200
    ri = RunInfo(run_id="t", runtype="run_R8520", run_dir=Path("/x"),
                 runinfo_path=Path("/x/runinfo.json"), raw_dir=Path("/x/RAW"))
    return RunData(runinfo=ri, data=None, dynode_records=dyn,
                   anode_records=ano, data_format="test")


def test_empty_match_df_returns_empty():
    run_data, _, _ = build_synthetic_run_data()
    empty = pd.DataFrame(columns=["dynode_idx", "anode_idx", "dt", "channel"])
    assert cluster_peaks(empty, run_data, build_config()) == []


def test_each_row_in_exactly_one_peak():
    run_data, _, _ = build_synthetic_run_data()
    df = match_events(run_data, build_config())
    peaks = cluster_peaks(df, run_data, build_config())
    assert len(peaks) > 0
    all_rows = sorted(r for p in peaks for r in p.match_rows)
    assert all_rows == sorted(range(len(df)))


def test_each_peak_has_anode_and_dynode():
    run_data, _, _ = build_synthetic_run_data()
    df = match_events(run_data, build_config())
    peaks = cluster_peaks(df, run_data, build_config())
    for p in peaks:
        assert p.n_anode >= 1
        assert p.n_dynode >= 1
        assert all(r.is_dynode for r in p.dynode_records)
        assert all(not r.is_dynode for r in p.anode_records)


def test_dynodes_within_window():
    run_data, _, _ = build_synthetic_run_data()
    cfg = build_config()
    win = float(cfg["clustering"]["window_ns"])
    df = match_events(run_data, cfg)
    peaks = cluster_peaks(df, run_data, cfg)
    for p in peaks:
        first = min(r.time_ns for r in p.dynode_records)
        assert all(r.time_ns <= first + win for r in p.dynode_records)


def test_sorted_and_sequential_ids():
    run_data, _, _ = build_synthetic_run_data()
    cfg = build_config()
    df = match_events(run_data, cfg)
    peaks = cluster_peaks(df, run_data, cfg)
    starts = [p.start_time_ns for p in peaks]
    assert starts == sorted(starts)
    assert [p.peaks_id for p in peaks] == list(range(len(peaks)))
    # each peak spans anode and dynode times consistently
    for p in peaks:
        assert p.end_time_ns >= p.start_time_ns


def test_multichannel_merging_within_window():
    cfg = build_config()
    # ch2@1000, ch3@1050 within window -> one peak; ch4@1200 > anchor+100 -> separate
    rd = _make_run_data(
        dyn_times=[1000, 1050, 1200],
        ano_times=[1006, 1056, 1206],
        dyn_ch=[2, 3, 4],
        ano_ch=[2, 3, 4],
    )
    df = match_events(rd, cfg)
    assert len(df) == 3
    peaks = cluster_peaks(df, rd, cfg)
    assert len(peaks) == 2
    first, second = peaks
    assert set(first.channels) == {2, 3}
    assert first.n_anode == 2 and first.n_dynode == 2
    assert first.start_time_ns == 1000.0
    assert set(second.channels) == {4}
    assert second.start_time_ns == 1200.0


def test_missing_time_field_raises():
    run_data, _, _ = build_synthetic_run_data()
    df = match_events(run_data, build_config())
    bad = np.zeros(1, dtype=[("channel", "i4")])
    rd = RunData(runinfo=run_data.runinfo, data=run_data.data,
                 dynode_records=bad, anode_records=run_data.anode_records,
                 data_format="test")
    with pytest.raises(ValueError):
        cluster_peaks(df, rd, build_config())
