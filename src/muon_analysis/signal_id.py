"""Peak-level signal discrimination.

Classification order is fixed and must not change:
**S1 -> S2 -> muon -> other**.  The three cuts are mutually exclusive.

  - ``"S1"``: a narrow, prompt-like peak -- **both** cuts satisfied:
    ``width_20_50area < w20_50area_max_ns`` (default 100 ns) **and**
    ``width_90area < w90area_max_ns`` (default 1000 ns).
  - ``"S2"``: a wide, delayed-like peak at low height -- **all** cuts satisfied:
    ``width_90area > w90area_min_ns``, ``width > width_min_ns``,
    ``anode_sum_area > anode_sum_area_min_pe`` and
    ``height < height_max_adc`` (default 15000 ADC).
  - ``"muon"``: a through-going muon candidate -- **all** cuts satisfied:
    ``n_channels >= n_channels_min`` (default 2),
    ``height > height_min_adc`` (default 15000 ADC),
    ``width > width_min_ns`` (default 2000 ns),
    ``width_90area > w90area_min_ns`` (default 1000 ns) and
    ``anode_sum_area > anode_sum_area_min_pe`` (default 300 PE).
  - ``"other"``: everything else (or excluded by an optional gate
    ``long_wave_min_samples``).

The earlier ``end_first``-based ``s1_width`` / ``s2_width`` criteria are
**void**: a muon tail keeps the summed waveform below the baseline-return
tolerance, so ``end_first`` falls back to the waveform end and the prompt and
delayed components cannot be separated that way -- see
``docs/end_first_muon_s1_issue.md``.  ``width`` is record-length limited for
muon peaks (see ``docs/other_muon_candidates_params.md``), so ``height`` /
``anode_sum_area`` / ``n_channels`` carry the discrimination.

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


def _is_muon(peak_features: PeakFeatures, n_channels: int, muon: Dict[str, Any]) -> bool:
    return (n_channels >= int(muon.get("n_channels_min", 2))
            and peak_features.height > float(muon.get("height_min_adc", 15000.0))
            and peak_features.width > float(muon.get("width_min_ns", 2000.0))
            and peak_features.width_90area > float(muon.get("w90area_min_ns", 1000.0))
            and peak_features.anode_sum_area > float(muon.get("anode_sum_area_min_pe", 300.0)))


def _is_s2(peak_features: PeakFeatures, s2: Dict[str, Any]) -> bool:
    return (peak_features.width_90area > float(s2.get("w90area_min_ns", 1000.0))
            and peak_features.width > float(s2.get("width_min_ns", 2000.0))
            and peak_features.anode_sum_area > float(s2.get("anode_sum_area_min_pe", 300.0))
            and peak_features.height < float(s2.get("height_max_adc", 15000.0)))


def classify_signal(
    peak_features: PeakFeatures,
    n_channels: int,
    config: Dict[str, Any],
) -> str:
    """Return the signal type of a peak (``S1`` / ``S2`` / ``muon`` / ``other``).

    The check order is **S1 -> S2 -> muon -> other** and must not change.
    """
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

    muon = cfg.get("muon", {}) or {}
    if _is_muon(peak_features, n_channels, muon):
        return "muon"

    return "other"
