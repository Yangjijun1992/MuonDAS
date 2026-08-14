"""Unit tests for COG position reconstruction and PMT pattern loading."""

from __future__ import annotations

import json

import pytest

from muon_analysis.cog import cog_reconstruct, cog_reconstruct_peak, load_pmt_pattern
from muon_analysis.models import PeakFeatures


def _write(tmp_path, name, content):
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return str(p)


def test_load_json_dict(tmp_path):
    path = _write(tmp_path, "pat.json", json.dumps({"pmt0": [1.0, 2.0], "pmt1": [3, 4, 5]}))
    pat = load_pmt_pattern(path)
    assert pat == {"pmt0": (1.0, 2.0, 0.0), "pmt1": (3.0, 4.0, 5.0)}


def test_load_json_list(tmp_path):
    path = _write(tmp_path, "pat.json", json.dumps([
        {"pmt_id": "pmt0", "x": 1.0, "y": 2.0},
        {"pmt_id": "pmt1", "x": 3.0, "y": 4.0, "z": 5.0},
    ]))
    pat = load_pmt_pattern(path)
    assert pat == {"pmt0": (1.0, 2.0, 0.0), "pmt1": (3.0, 4.0, 5.0)}


def test_load_csv(tmp_path):
    path = _write(tmp_path, "pat.csv", "pmt_id,x,y,z\npmt0,1,2,\npmt1,3,4,5\n")
    pat = load_pmt_pattern(path)
    assert pat["pmt0"] == (1.0, 2.0, 0.0)
    assert pat["pmt1"] == (3.0, 4.0, 5.0)


def test_load_yaml(tmp_path):
    path = _write(tmp_path, "pat.yaml", "pmt0: [1.0, 2.0]\npmt1: [3, 4, 5]\n")
    pat = load_pmt_pattern(path)
    assert pat == {"pmt0": (1.0, 2.0, 0.0), "pmt1": (3.0, 4.0, 5.0)}


def test_load_auto_format(tmp_path):
    path = _write(tmp_path, "pat.yml", "pmt0: [1.0, 2.0]\n")
    pat = load_pmt_pattern(path, fmt="auto")
    assert pat == {"pmt0": (1.0, 2.0, 0.0)}


def test_load_empty_raises(tmp_path):
    path = _write(tmp_path, "pat.json", "{}")
    with pytest.raises(ValueError):
        load_pmt_pattern(path)


def test_load_missing_file_raises(tmp_path):
    with pytest.raises(ValueError):
        load_pmt_pattern(str(tmp_path / "nope.json"))


def test_centroid_two_points_equal_weights():
    pat = {"a": (0.0, 0.0), "b": (4.0, 2.0)}
    x, y = cog_reconstruct({"a": 1.0, "b": 1.0}, pat)
    assert x == pytest.approx(2.0)
    assert y == pytest.approx(1.0)


def test_centroid_three_points_weighted():
    pat = {"a": (0.0, 0.0), "b": (4.0, 0.0), "c": (0.0, 4.0)}
    x, y = cog_reconstruct({"a": 1.0, "b": 1.0, "c": 2.0}, pat)
    # weighted mean: x=(1*0+1*4+2*0)/4=1, y=(1*0+1*0+2*4)/4=2
    assert x == pytest.approx(1.0)
    assert y == pytest.approx(2.0)


def test_missing_pmt_skipped():
    pat = {"a": (0.0, 0.0), "b": (4.0, 2.0)}
    # "c" has charge but no pattern entry -> skipped; "a" zero weight -> skipped
    x, y = cog_reconstruct({"a": 0.0, "b": 1.0, "c": 5.0}, pat)
    assert x == pytest.approx(4.0)
    assert y == pytest.approx(2.0)


def test_no_usable_charge_raises():
    pat = {"a": (0.0, 0.0)}
    with pytest.raises(ValueError):
        cog_reconstruct({"a": 0.0}, pat)
    with pytest.raises(ValueError):
        cog_reconstruct({}, pat)


def test_cog_reconstruct_peak_empty_returns_none():
    feats = PeakFeatures(peaks_id=1, time_ns=0.0, channels=[], anode_record_ids=[], dynode_record_ids=[], charge_per_pmt={})
    assert cog_reconstruct_peak(feats, None, {"a": (0.0, 0.0)}, {}) is None


def test_cog_reconstruct_peak_returns_centroid():
    feats = PeakFeatures(
        peaks_id=1, time_ns=0.0, channels=[], anode_record_ids=[], dynode_record_ids=[],
        charge_per_pmt={"a": 1.0, "b": 1.0},
    )
    x, y = cog_reconstruct_peak(feats, None, {"a": (0.0, 0.0), "b": (4.0, 2.0)}, {})
    assert x == pytest.approx(2.0)
    assert y == pytest.approx(1.0)


def _cfg(pattern_path="", use_fallback=False):
    return {"cog": {"pattern_path": pattern_path, "pattern_format": "auto",
                    "use_fallback": use_fallback}}


def test_load_layout_from_file(tmp_path):
    from muon_analysis.cog import load_pmt_layout
    path = _write(tmp_path, "pat.json", json.dumps({"pmt0": [1.0, 2.0]}))
    layout = load_pmt_layout(_cfg(pattern_path=path))
    assert layout.source == "file"
    assert layout.pmt_positions_by_id == {"pmt0": (1.0, 2.0)}


def test_load_layout_from_runinfo():
    from pathlib import Path
    from muon_analysis.cog import load_pmt_layout
    from muon_analysis.models import RunInfo
    ri = RunInfo(
        run_id="00179", runtype="t", run_dir=Path("/x"),
        runinfo_path=Path("/x"), raw_dir=Path("/x"),
        metadata={"mapping": [{"board_id": 0, "channels": [
            {"ch": 0, "pmt": "pmt0", "pos": [0.0, 0.0]},
            {"ch": 1, "pmt": "pmt1", "pos": [10.0, 5.0]},
        ]}]},
    )
    layout = load_pmt_layout(_cfg(), ri)
    assert layout is not None
    assert layout.source == "runinfo"
    assert layout.pmt_positions_by_id == {"pmt0": (0.0, 0.0), "pmt1": (10.0, 5.0)}


def test_load_layout_runinfo_no_pos_skipped():
    from pathlib import Path
    from muon_analysis.cog import load_pmt_layout
    from muon_analysis.models import RunInfo
    ri = RunInfo(
        run_id="00179", runtype="t", run_dir=Path("/x"),
        runinfo_path=Path("/x"), raw_dir=Path("/x"),
        metadata={"mapping": [{"board_id": 0, "channels": [
            {"ch": 0, "pmt": "unknown_pmt"},  # no pos, no fallback -> skipped
        ]}]},
    )
    assert load_pmt_layout(_cfg(), ri) is None


def test_load_layout_fallback():
    from muon_analysis.cog import load_pmt_layout
    layout = load_pmt_layout(_cfg(use_fallback=True))
    assert layout.source == "fallback"
    assert len(layout.entries) == 7
    assert layout.pmt_positions_by_id["LV2332"] == (0.0, 0.0)


def test_load_layout_none_without_source():
    from muon_analysis.cog import load_pmt_layout
    assert load_pmt_layout(_cfg()) is None


def test_layout_entry_lookups():
    from muon_analysis.cog import load_pmt_layout
    layout = load_pmt_layout(_cfg(use_fallback=True))
    entry = layout.entry_for_pmt("LV2332")
    assert entry.xy_mm == (0.0, 0.0)
    assert layout.entry_for_readout(0, 12) is entry
    assert layout.entry_for_readout(0, 999) is None
