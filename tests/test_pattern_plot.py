"""Tests for the PMT pattern area-map plot (plotting/pattern.py)."""

from __future__ import annotations

from muon_analysis.cog import _layout_from_fallback, PmtLayout, PmtEntry
from muon_analysis.plotting.pattern import plot_pmt_area_map


def test_plot_pmt_area_map_fallback_layout(tmp_path):
    layout = _layout_from_fallback()
    charge = {e.pmt_id: float(i + 1) for i, e in enumerate(layout.entries)}
    p = plot_pmt_area_map(layout, charge, tmp_path, "00179", index=3)
    assert p.exists()
    assert p.name == "pmt_area_run_00179__3.png"


def test_plot_pmt_area_map_zero_charge(tmp_path):
    layout = _layout_from_fallback()
    p = plot_pmt_area_map(layout, {}, tmp_path, "00179")
    assert p.exists()
    assert p.name == "pmt_area_run_00179.png"


def test_plot_pmt_area_map_partial_charge(tmp_path):
    entries = (PmtEntry(pmt_id="a", x_mm=0.0, y_mm=0.0, pmt_no=1),
               PmtEntry(pmt_id="b", x_mm=10.0, y_mm=0.0, pmt_no=2))
    layout = PmtLayout(entries=entries, source="test")
    p = plot_pmt_area_map(layout, {"a": 3.0}, tmp_path, "00179", index=0)
    assert p.exists()
    assert "pmt_area_run_00179__0.png" in p.name
