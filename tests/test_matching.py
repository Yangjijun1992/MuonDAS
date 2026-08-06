import numpy as np
import pandas as pd

from muon_analysis.matching import match_events, get_matched_indices_by_channel
from muon_analysis.config import build_config


def test_merge_asof_by_channel():
    ano = np.zeros(5, dtype=[("time", "i8"), ("channel", "i4")])
    dyn = np.zeros(5, dtype=[("time", "i8"), ("channel", "i4")])
    ano["time"] = [100, 200, 300, 400, 500]
    ano["channel"] = [0, 1, 0, 1, 0]
    dyn["time"] = [110, 210, 315, 405, 505]
    dyn["channel"] = [0, 1, 0, 1, 0]
    df = get_matched_indices_by_channel(ano, dyn, 0, 30)
    assert list(df.columns) == ["dynode_idx", "anode_idx", "dt", "channel"]
    assert len(df) > 0
    assert (df["dt"] >= 0).all() and (df["dt"] <= 30).all()


def test_match_events_full(conftest_run_data):
    run_data, _, _ = conftest_run_data
    cfg = build_config()
    df = match_events(run_data, cfg)
    assert isinstance(df, pd.DataFrame)
    # all pairs should match within the window
    assert len(df) > 0
    assert (df["dt"] >= cfg["matching"]["min_diff_ns"]).all()
    assert (df["dt"] <= cfg["matching"]["max_diff_ns"]).all()
