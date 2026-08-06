import numpy as np
import pandas as pd

from muon_analysis.plotting.distributions import plot_correlation, plot_distributions
from muon_analysis.plotting.waveforms import apply_lowpass_filter


def test_plot_distributions(tmp_path):
    n = 50
    df = pd.DataFrame({
        "channel": [0] * n,
        "anode_area_pe": np.random.rand(n) * 100,
        "dynode_area_pe": np.random.rand(n) * 10,
        "anode_seg_area_pe": np.random.rand(n) * 20000,
        "event_length": np.full(n, 7000),
        "dt_ns": np.random.rand(n),
    })
    saved = plot_distributions(df, tmp_path, "00179")
    assert len(saved) >= 3
    for p in saved:
        assert p.exists()


def test_plot_correlation(tmp_path):
    n = 10
    a = pd.DataFrame({"channel": [0] * n, "anode_area_pe": np.arange(n)})
    d = pd.DataFrame({"channel": [0] * n, "dynode_area_pe": np.arange(n)})
    p = plot_correlation(a, d, tmp_path, "00179")
    assert p.exists()


def test_lowpass_filter_shape():
    wf = np.random.rand(200)
    out = apply_lowpass_filter(wf)
    assert out.shape == wf.shape
    # 2D
    wfs = np.random.rand(3, 200)
    out2 = apply_lowpass_filter(wfs)
    assert out2.shape == wfs.shape
