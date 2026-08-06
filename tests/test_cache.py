import numpy as np
import pytest
from unittest import mock

from muon_analysis import cache
from muon_analysis.config import build_config
from muon_analysis.cache import CacheWarning


def test_cache_key_param_hashed():
    cfg = build_config()
    k1 = cache.cache_key("00179", cfg)
    k2 = cache.cache_key("00179", cfg)
    k3 = cache.cache_key("00180", cfg)
    assert k1 == k2
    assert k1 != k3
    assert "00179" in k1


def test_write_read_npy(tmp_path):
    cfg = build_config(overrides={"output": {"cache_dir": str(tmp_path)}})
    arr = np.arange(10)
    path = cache.write_npy("00179", cfg, arr, ext="_match.npy")
    assert path.exists()
    read = cache.read_npy("00179", cfg, ext="_match.npy")
    assert np.array_equal(read, arr)
    # wrong hash -> miss
    cfg2 = build_config(overrides={"output": {"cache_dir": str(tmp_path)},
                                   "matching": {"max_diff_ns": 40}})
    assert cache.read_npy("00179", cfg2, ext="_match.npy") is None


def test_clear_and_show(tmp_path, capsys):
    cfg = build_config(overrides={"output": {"cache_dir": str(tmp_path)}})
    cache.write_npy("00179", cfg, np.zeros(3), ext="_match.npy")
    cache.show_cache(cfg)
    assert "00179" in capsys.readouterr().out
    n = cache.clear_cache(cfg)
    assert n == 1
    assert cache.list_cache(cfg) == []


def test_low_space_warning(tmp_path):
    import collections
    import shutil
    DU = collections.namedtuple("usage", "total used free")
    with mock.patch.object(shutil, "disk_usage",
                           return_value=DU(0, 0, 1_000_000)):
        with pytest.warns(CacheWarning):
            cache.ensure_cache_ready(tmp_path)
