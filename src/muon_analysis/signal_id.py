"""Peak-level signal discrimination.

Classification (checked in order):

  - ``"S1"``: a narrow, prompt-like peak -- **both** cuts satisfied:
    ``width_20_50area < w20_50area_max_ns`` (default 100 ns) **and**
    ``width_90area < w90area_max_ns`` (default 1000 ns).
  - ``"S2"``: a wide, delayed-like peak -- **all** cuts satisfied:
    ``width_90area > w90area_min_ns`` (default 1000 ns),
    ``width_ns > width_ns_min_ns`` (default 2000 ns),
    ``anode_sum_area > anode_sum_area_min_pe`` (default 300 PE) and
    ``height < height_max_adc`` (default 15000 ADC).
  - ``"other"``: everything else (peaks excluded by an optional gate
    -- ``long_wave_min_samples`` or ``n_channels`` -- or matching neither).

The earlier ``end_first``-based ``s1_width`` / ``s2_width`` criteria are
**void**: a muon tail keeps the summed waveform below the baseline-return
tolerance, so ``end_first`` falls back to the waveform end and the prompt and
delayed components cannot be separated that way -- see
``docs/end_first_muon_s1_issue.md``.

Thresholds are configurable under ``config["signal_id"]``.
"""

from __future__ import annotations

from typing import Any, Dict

from muon_analysis.models import PeakFeatures


def _channel_gate_ok(cfg: Dict[str, Any], n_channels: int) -> bool:
    n_ch = cfg.get("n_channels")
    return n_ch is None or n_channels == int(n_ch)


def _is_s1(peak_features: PeakFeatures, s1: Dict[str, Any]) -> bool:
    return (peak_features.width_20_50area < float(s1.get("w20_50area_max_ns", 100.0))
            and peak_features.width_90area < float(s1.get("w90area_max_ns", 1000.0)))


def _is_s2(peak_features: PeakFeatures, s2: Dict[str, Any]) -> bool:
    return (peak_features.width_90area > float(s2.get("w90area_min_ns", 1000.0))
            and peak_features.width_ns > float(s2.get("width_ns_min_ns", 2000.0))
            and peak_features.anode_sum_area > float(s2.get("anode_sum_area_min_pe", 300.0))
            and peak_features.height < float(s2.get("height_max_adc", 15000.0)))


def classify_signal(
    peak_features: PeakFeatures,
    n_channels: int,
    config: Dict[str, Any],
) -> str:
    """Return the signal type of a peak (``S1`` / ``S2`` / ``other``)."""
    cfg = (config or {}).get("signal_id", {}) or {}

    long_min = cfg.get("long_wave_min_samples")
    if long_min is not None and peak_features.wave_len_samples <= int(long_min):
        return "other"

    s1 = cfg.get("s1", {}) or {}
    if _channel_gate_ok(s1, n_channels) and _is_s1(peak_features, s1):
        return "S1"

    s2 = cfg.get("s2", {}) or {}
    if _channel_gate_ok(s2, n_channels) and _is_s2(peak_features, s2):
        return "S2"

    return "other"
