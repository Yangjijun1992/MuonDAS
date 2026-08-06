from muon_analysis.config import build_config, param_hash, ConfigError


def test_default_config():
    cfg = build_config()
    assert cfg["features"]["integral_window_mode"] == "fixed"
    assert cfg["matching"]["max_diff_ns"] == 30


def test_invalid_window_mode():
    try:
        build_config(overrides={"features": {"integral_window_mode": "bogus"}})
        raise AssertionError("expected ConfigError")
    except ConfigError:
        pass


def test_invalid_fixed_window():
    try:
        build_config(overrides={"features": {"integral_window_mode": "fixed",
                                             "integral_start": 100,
                                             "integral_end": 50}})
        raise AssertionError("expected ConfigError")
    except ConfigError:
        pass


def test_override_precedence():
    cfg = build_config(overrides={"features": {"integral_start": 5}})
    assert cfg["features"]["integral_start"] == 5


def test_param_hash_stable_and_volatile():
    cfg = build_config()
    assert param_hash(cfg) == param_hash(cfg)
    cfg2 = build_config(overrides={"matching": {"max_diff_ns": 40}})
    assert param_hash(cfg) != param_hash(cfg2)
