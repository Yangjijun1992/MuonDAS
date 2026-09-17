"""Tests for the width-cut based signal discrimination."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from types import SimpleNamespace

from muon_analysis.config import build_config
from muon_analysis.signal_id import classify_signal


def _feats(w20_50area=10.0, w90area=100.0, wave_len=1000):
    return SimpleNamespace(width_20_50area=w20_50area,
                           width_90area=w90area,
                           wave_len_samples=wave_len)


def _cfg():
    cfg = build_config()
    cfg["signal_id"]["long_wave_min_samples"] = None
    cfg["signal_id"]["muon_s1"]["n_channels"] = None
    cfg["signal_id"]["muon_s2"]["n_channels"] = None
    return cfg


def test_narrow_peak_is_muon_s1():
    assert classify_signal(_feats(10.0, 100.0), 7, _cfg()) == "muon_s1"


def test_w20_50area_over_cut_is_muon_s2():
    assert classify_signal(_feats(150.0, 100.0), 7, _cfg()) == "muon_s2"


def test_w90area_over_cut_is_muon_s2():
    assert classify_signal(_feats(10.0, 1500.0), 7, _cfg()) == "muon_s2"


def test_both_cuts_must_hold():
    assert classify_signal(_feats(150.0, 1500.0), 7, _cfg()) == "muon_s2"


def test_cut_boundaries_are_exclusive():
    cfg = _cfg()
    assert classify_signal(_feats(99.9, 999.9), 7, cfg) == "muon_s1"
    assert classify_signal(_feats(100.0, 999.9), 7, cfg) == "muon_s2"
    assert classify_signal(_feats(99.9, 1000.0), 7, cfg) == "muon_s2"


def test_long_wave_gate_yields_other():
    cfg = _cfg()
    cfg["signal_id"]["long_wave_min_samples"] = 5000
    assert classify_signal(_feats(10.0, 100.0, wave_len=4000), 7, cfg) == "other"
    assert classify_signal(_feats(10.0, 100.0, wave_len=6000), 7, cfg) == "muon_s1"


def test_n_channels_gate_yields_other():
    cfg = _cfg()
    cfg["signal_id"]["muon_s1"]["n_channels"] = 7
    cfg["signal_id"]["muon_s2"]["n_channels"] = 7
    assert classify_signal(_feats(10.0, 100.0), 3, cfg) == "other"
    assert classify_signal(_feats(150.0, 100.0), 3, cfg) == "other"
    assert classify_signal(_feats(10.0, 100.0), 7, cfg) == "muon_s1"
