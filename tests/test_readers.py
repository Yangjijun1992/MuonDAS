import numpy as np
from types import SimpleNamespace

from muon_analysis.io.readers import summarize_raw_data


def _records(n=100):
    return np.zeros(n, dtype=[
        ("time", "i8"), ("channel", "i4"), ("board", "i4"),
        ("record_id", "i8"), ("event_length", "i4"),
    ])


def test_summarize_includes_waveform_count():
    rec = _records(120)
    rec["time"] = np.arange(120) * 100  # 0..11900 ns
    rec["channel"] = 0
    rec["board"] = 0
    rec["event_length"] = 64
    data = SimpleNamespace(records=rec)
    summary = summarize_raw_data(data)
    assert summary["event_count"] == 120
    assert summary["waveform_count"] == 120
    assert summary["channel_count"] == 1
    assert "board_count" in summary


def test_summarize_channels_boards():
    rec = _records(8)
    rec["channel"] = [0, 1, 2, 3, 0, 1, 2, 3]
    rec["board"] = [0, 0, 0, 0, 1, 1, 1, 1]
    data = SimpleNamespace(records=rec)
    summary = summarize_raw_data(data)
    assert summary["channel_count"] == 4
    assert summary["boards"] == [0, 1]
