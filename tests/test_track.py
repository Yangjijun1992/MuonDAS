"""Unit tests for muon track reconstruction (time slicing + 3D track)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np

from muon_analysis.io.data import RunData
from muon_analysis.models import Peak, PeakRecord, RunInfo
from muon_analysis.track import Track3D, plot_track, reconstruct_track, slice_peak_waveforms
from tests.conftest import make_waveform


def _run_data_with_dynodes(tmp_path):
    """A RunData with two dynode records on channels 0/1, pulsing in diff slices."""
    length = 500
    wf0 = make_waveform(length=length, amplitude=100.0, start=50, seed=1, noise=0.0)
    wf1 = make_waveform(length=length, amplitude=80.0, start=300, seed=2, noise=0.0)
    store = {1000: wf0, 1001: wf1}

    dyn_dtype = [("time", "i8"), ("channel", "i4"), ("board", "i4"),
                 ("record_id", "i8"), ("event_length", "i4")]
    dyn_rec = np.zeros(2, dtype=dyn_dtype)
    dyn_rec["time"] = [0, 0]
    dyn_rec["channel"] = [0, 1]
    dyn_rec["board"] = 1
    dyn_rec["record_id"] = [1000, 1001]
    dyn_rec["event_length"] = length
    ano_rec = np.zeros(0, dtype=dyn_dtype)

    data = SimpleNamespace(records=np.concatenate([ano_rec, dyn_rec]), signals=None)
    data.signals = lambda ids: np.stack([store[int(i)] for i in ids])

    ri = RunInfo(
        run_id="00179", runtype="run_R8520", run_dir=Path("/x"),
        runinfo_path=Path("/x/runinfo.json"), raw_dir=Path("/x/RAW"),
        metadata={
            "mapping": [
                {"board_id": 1, "channels": [
                    {"ch": 0, "pmt": "pmt0"},
                    {"ch": 1, "pmt": "pmt1"},
                ]}
            ]
        },
    )
    run_data = RunData(runinfo=ri, data=data, dynode_records=dyn_rec,
                       anode_records=ano_rec, data_format="test")
    return run_data


def _config():
    return {
        "track": {"slice_us": 1.0, "fs": 250e6},
        "plotting": {"dynode_scale": 110, "dynode_lp_cutoff_hz": None},
    }


def _peak_dynodes():
    rec0 = PeakRecord(record_id=1000, channel=0, time_ns=0.0, is_dynode=True)
    rec1 = PeakRecord(record_id=1001, channel=1, time_ns=0.0, is_dynode=True)
    return Peak(
        peaks_id=5, start_time_ns=0.0, end_time_ns=3000.0,
        dynode_records=[rec0, rec1],
        channels=[0, 1],
    )


def test_slice_peak_waveforms_has_charge(tmp_path):
    run_data = _run_data_with_dynodes(tmp_path)
    peak = _peak_dynodes()
    slices = slice_peak_waveforms(peak, run_data, _config())
    assert len(slices) > 0

    def max_charge_slice(ch):
        return max(
            (s for s in slices if s["charge_per_channel"].get(ch, 0.0) > 0),
            key=lambda s: s["charge_per_channel"][ch],
        )["slice_index"]

    assert max_charge_slice(0) < max_charge_slice(1)
    for s in slices:
        assert s["time_ns"] >= 0.0


def test_reconstruct_track(tmp_path):
    run_data = _run_data_with_dynodes(tmp_path)
    peak = _peak_dynodes()
    slices = slice_peak_waveforms(peak, run_data, _config())
    pattern = {"pmt0": (0.0, 0.0), "pmt1": (1.0, 1.0)}
    track = reconstruct_track(slices, run_data.runinfo, pattern, _config())
    assert isinstance(track, Track3D)
    assert track.n_slices > 0
    assert track.n_slices == len(track.slice_centers) == len(track.slice_times_ns)
    for (x, y) in track.slice_centers:
        assert np.isfinite(x) and np.isfinite(y)


def test_plot_track_saves_png(tmp_path):
    track = Track3D(peaks_id=5, slice_centers=[(0.0, 0.0), (1.0, 1.0)],
                    slice_times_ns=[0.0, 1000.0])
    out = tmp_path / "plots"
    path = plot_track(track, out, "00179")
    assert path.exists()
    assert path.name == "track_run_00179.png"
