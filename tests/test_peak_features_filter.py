import numpy as np
import pytest

from conftest import build_synthetic_run_data, make_gain_db
from muon_analysis.config import build_config
from muon_analysis.features import compute_peak_features
from muon_analysis.filtering import filter_muon_candidates


def _peaks(run_data, cfg):
    from muon_analysis.matching import match_events
    from muon_analysis.clustering import cluster_peaks
    match_df = match_events(run_data, cfg)
    return cluster_peaks(match_df, run_data, cfg)


def _features(run_data, peaks, cfg, db):
    return [compute_peak_features(p, run_data, db, cfg) for p in peaks]


def test_peak_features():
    cfg = build_config()
    run_data, _, _ = build_synthetic_run_data()
    db = make_gain_db()
    peaks = _peaks(run_data, cfg)
    assert len(peaks) > 0
    for peak in peaks:
        pf = compute_peak_features(peak, run_data, db, cfg)
        assert pf.anode_area_pe > 0
        assert pf.dynode_area_pe > 0
        assert pf.peak_height > 0
        assert set(pf.anode_features) == set(pf.anode_record_ids)
        assert set(pf.dynode_features) == set(pf.dynode_record_ids)


def test_dynode_scale_applied():
    cfg = build_config(overrides={"plotting": {"dynode_lp_cutoff_hz": None}})
    run_data, _, _ = build_synthetic_run_data()
    db = make_gain_db()
    peaks = _peaks(run_data, cfg)
    accessor = run_data.signals
    from muon_analysis.plotting.waveforms import apply_lowpass_filter
    plot_cfg = cfg["plotting"]
    lp_cutoff = plot_cfg.get("dynode_lp_cutoff_hz")
    fs = float(plot_cfg.get("fs", 250e6))
    dynode_scale = float(plot_cfg.get("dynode_scale", 110))
    for peak in peaks[:3]:
        pf = compute_peak_features(peak, run_data, db, cfg)
        for rec in peak.dynode_records:
            raw = np.asarray(accessor([rec.record_id])).reshape(-1)
            if lp_cutoff is not None:
                raw = apply_lowpass_filter(raw, cutoff_hz=float(lp_cutoff),
                                           fs=fs, order=4)
            raw_amp = float(np.max(raw) - np.mean(raw[:10]))
            dyn_height = pf.dynode_features[rec.record_id].height
            assert dyn_height == pytest.approx(raw_amp * dynode_scale, rel=0.05)


def test_filter_pass_all():
    cfg = build_config()  # all peak-level filters None => relaxed
    run_data, _, _ = build_synthetic_run_data()
    db = make_gain_db()
    peaks = _peaks(run_data, cfg)
    feats = _features(run_data, peaks, cfg, db)
    candidates = filter_muon_candidates(peaks, feats, cfg)
    assert len(candidates) == len(peaks)
    for c in candidates:
        assert all(c.passed_conditions.values())


def test_filter_height_cut():
    cfg = build_config()
    run_data, _, _ = build_synthetic_run_data()
    db = make_gain_db()
    peaks = _peaks(run_data, cfg)
    feats = _features(run_data, peaks, cfg, db)
    max_height = max(pf.peak_height for pf in feats)

    cfg_hard = build_config(overrides={"filtering": {"height_min": max_height + 1}})
    assert filter_muon_candidates(peaks, feats, cfg_hard) == []

    cfg_zero = build_config(overrides={"filtering": {"height_min": 0}})
    assert len(filter_muon_candidates(peaks, feats, cfg_zero)) == len(peaks)


def test_filter_pe_cut():
    cfg = build_config()
    run_data, _, _ = build_synthetic_run_data()
    db = make_gain_db()
    peaks = _peaks(run_data, cfg)
    feats = _features(run_data, peaks, cfg, db)
    max_anode = max(pf.anode_area_pe for pf in feats)

    cfg_hard = build_config(
        overrides={"filtering": {"min_area_pe_anode": max_anode * 2}})
    assert filter_muon_candidates(peaks, feats, cfg_hard) == []

    cfg_zero = build_config(overrides={"filtering": {"min_area_pe_anode": 0}})
    assert len(filter_muon_candidates(peaks, feats, cfg_zero)) == len(peaks)


def test_filter_missing_features_raises():
    cfg = build_config()
    run_data, _, _ = build_synthetic_run_data()
    peaks = _peaks(run_data, cfg)
    with pytest.raises(ValueError):
        filter_muon_candidates(peaks, [], cfg)
