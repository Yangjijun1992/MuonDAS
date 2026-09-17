"""Tests for the width-cut based signal discrimination."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from types import SimpleNamespace

from muon_analysis.config import build_config
from muon_analysis.signal_id import classify_signal

NARROW = dict(width_20_50area=10.0, width_90area=100.0, width_ns=300.0,
              anode_sum_area=200.0, height=2000.0, wave_len_samples=1000)
S2 = dict(width_20_50area=5000.0, width_90area=6000.0, width_ns=10000.0,
          anode_sum_area=8000.0, height=5000.0, wave_len_samples=3000)
MUON = dict(width_20_50area=5000.0, width_90area=19000.0, width_ns=26000.0,
            anode_sum_area=30000.0, height=60000.0, wave_len_samples=6700)


def _feats(**over):
    return SimpleNamespace(**{**NARROW, **over})


def _cfg():
    cfg = build_config()
    cfg["signal_id"]["long_wave_min_samples"] = None
    cfg["signal_id"]["s1"]["n_channels"] = None
    cfg["signal_id"]["s2"]["n_channels"] = None
    return cfg


def test_narrow_peak_is_s1():
    assert classify_signal(_feats(), 7, _cfg()) == "S1"


def test_s2_peak_needs_all_four_cuts():
    cfg = _cfg()
    assert classify_signal(_feats(**S2), 7, cfg) == "S2"
    assert classify_signal(_feats(**{**S2, "height": 50000.0}), 7, cfg) == "muon"
    violations = {"width_90area": 100.0, "width_ns": 300.0, "anode_sum_area": 200.0}
    for key, bad in violations.items():
        over = dict(S2)
        over[key] = bad
        assert classify_signal(_feats(**over), 7, cfg) == "other", key


def test_wide_but_high_is_muon():
    cfg = _cfg()
    assert classify_signal(_feats(**{**S2, "height": 50000.0}), 7, cfg) == "muon"


def test_wide_but_low_area_is_other():
    cfg = _cfg()
    assert classify_signal(_feats(**{**S2, "anode_sum_area": 100.0}), 7, cfg) == "other"


def test_s1_cut_boundaries_are_exclusive():
    cfg = _cfg()
    assert classify_signal(_feats(width_20_50area=99.9, width_90area=999.9), 7, cfg) == "S1"
    assert classify_signal(_feats(width_20_50area=100.0, width_90area=999.9), 7, cfg) == "other"
    assert classify_signal(_feats(width_20_50area=99.9, width_90area=1000.0), 7, cfg) == "other"


def test_long_wave_gate_yields_other():
    cfg = _cfg()
    cfg["signal_id"]["long_wave_min_samples"] = 5000
    assert classify_signal(_feats(wave_len_samples=4000), 7, cfg) == "other"
    assert classify_signal(_feats(wave_len_samples=6000), 7, cfg) == "S1"


def test_n_channels_gate_yields_other():
    cfg = _cfg()
    cfg["signal_id"]["s1"]["n_channels"] = 7
    cfg["signal_id"]["s2"]["n_channels"] = 7
    assert classify_signal(_feats(), 3, cfg) == "other"
    assert classify_signal(_feats(**S2), 3, cfg) == "other"
    assert classify_signal(_feats(), 7, cfg) == "S1"


def test_muon_peak_needs_all_cuts():
    cfg = _cfg()
    assert classify_signal(_feats(**MUON), 7, cfg) == "muon"
    assert classify_signal(_feats(**{**MUON, "height": 10000.0}), 7, cfg) == "S2"
    violations = {"width_ns": 300.0, "width_90area": 100.0, "anode_sum_area": 200.0}
    for key, bad in violations.items():
        over = dict(MUON)
        over[key] = bad
        assert classify_signal(_feats(**over), 7, cfg) == "other", key


def test_muon_requires_two_channels():
    cfg = _cfg()
    assert classify_signal(_feats(**MUON), 1, cfg) == "other"
    assert classify_signal(_feats(**MUON), 2, cfg) == "muon"


def test_muon_and_s2_are_height_disjoint():
    cfg = _cfg()
    assert classify_signal(_feats(**{**MUON, "height": 14000.0}), 7, cfg) == "S2"
    assert classify_signal(_feats(**{**S2, "height": 16000.0}), 7, cfg) == "muon"
