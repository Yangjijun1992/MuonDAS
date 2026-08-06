import numpy as np

from muon_analysis.config import build_config
from muon_analysis.filtering import asymmetry_calculation, filter_candidates


def _relaxed_config():
    return build_config(overrides={
        "filtering": {
            "min_event_length": 0,
            "min_seg_area_pe": None,
            "signal_positive_polarity": {"asym_min": 0.0},
            "signal_negative_polarity": {"asym_min": 0.0},
        },
        "features": {"integral_start": 15, "integral_end": 100},
    })


def test_asymmetry_calculation(conftest_run_data):
    run_data, _, _ = conftest_run_data
    from muon_analysis.filtering import SignalAccessor
    acc = SignalAccessor.from_run_data(run_data)
    result = asymmetry_calculation(run_data.anode_records, acc, "negative")
    assert "asym" in result.dtype.names
    # negative pulses => asym near 1 (strong signal)
    assert float(np.mean(result["asym"])) > 0.5


def test_filter_candidates(conftest_run_data):
    from conftest import make_gain_db
    run_data, _, _ = conftest_run_data
    from muon_analysis.matching import match_events
    cfg = _relaxed_config()
    match_df = match_events(run_data, cfg)
    db = make_gain_db([1e6, 1e6, 1e6, 1e6])
    candidates = filter_candidates(match_df, run_data, db, cfg)
    assert len(candidates) > 0
    for c in candidates:
        assert c.anode_area_pe > 0
        assert c.event_length > 0
