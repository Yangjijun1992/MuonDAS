import numpy as np
import pytest

from muon_analysis.features import (
    FixedWindowResolver,
    build_window_resolver,
    compute_features,
    integrate_area,
)
from muon_analysis.config import build_config


def test_fixed_window_resolve():
    r = FixedWindowResolver(20, 100)
    assert r.resolve(np.zeros(200)) == (20, 100)
    # truncate past end
    assert r.resolve(np.zeros(50)) == (20, 50)


def test_build_window_resolver_fixed():
    cfg = build_config()
    r = build_window_resolver(cfg)
    assert isinstance(r, FixedWindowResolver)


def test_build_window_resolver_peak_finder_placeholder():
    cfg = build_config(overrides={"features": {"integral_window_mode": "peak_finder"}})
    r = build_window_resolver(cfg)
    # falls back to fixed behaviour while no peak finder supplied
    assert r.resolve(np.zeros(200)) == (20, 100)


def test_integrate_area_positive_negative():
    wf = np.zeros(200)
    wf[20:80] = 1.0
    r = FixedWindowResolver(20, 80)
    assert integrate_area(wf, r, "positive") == pytest.approx(60.0)
    assert integrate_area(-wf, r, "negative") == pytest.approx(60.0)


def test_compute_features_gaussian():
    wf = np.zeros(200)
    wf[20:80] += np.exp(-((np.arange(60) - 30) ** 2) / 50.0) * 100
    feats, peak = compute_features(wf)
    assert feats.height == pytest.approx(100.0)
    assert feats.rise_time > 0
    assert feats.width > 0
    assert feats.charge > 0
