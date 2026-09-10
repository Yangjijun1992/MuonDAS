"""Peak-level signal discrimination.

After the peak-level parameters are computed, classify each peak into a signal
type.  The current rule set marks a peak as ``"muon_s1"`` when it satisfies the
muon-S1 selection (7-channel coincidence with a medium-energy, narrow pulse
shape); everything else is ``"other"``.  Thresholds are configurable under
``config["signal_id"]["muon_s1"]``.
"""

from __future__ import annotations

from typing import Any, Dict

from muon_analysis.models import PeakFeatures


def classify_signal(
    peak_features: PeakFeatures,
    n_channels: int,
    config: Dict[str, Any],
) -> str:
    """Return the signal type of a peak.

    Types (checked in order):

      - ``"muon_s1"``: 7-channel coincidence, narrow pulse
        (``width_20_50area < width_20_50area_max``, default 80 ns),
        ``anode_sum_area > anode_sum_area_min`` (300 PE),
        ``height >= height_min`` (4000 ADC),
        ``width_90area < width_90area_max`` (500 ns).
      - ``"muon_s2"``: 7-channel coincidence, wide pulse
        (``width_20_50area > width_20_50area_min``, default 80 ns),
        ``anode_sum_area > anode_sum_area_min`` (300 PE).
      - ``"other"``: everything else.
    """
    cfg = (config or {}).get("signal_id", {}) or {}

    s1 = cfg.get("muon_s1", {}) or {}
    if n_channels == int(s1.get("n_channels", 7)) \
            and peak_features.width_20_50area < float(s1.get("width_20_50area_max", 80.0)) \
            and peak_features.anode_sum_area > float(s1.get("anode_sum_area_min", 300.0)) \
            and peak_features.height >= float(s1.get("height_min", 4000.0)) \
            and peak_features.width_90area < float(s1.get("width_90area_max", 500.0)):
        return "muon_s1"

    s2 = cfg.get("muon_s2", {}) or {}
    if n_channels == int(s2.get("n_channels", 7)) \
            and peak_features.width_20_50area > float(s2.get("width_20_50area_min", 80.0)) \
            and peak_features.anode_sum_area > float(s2.get("anode_sum_area_min", 300.0)):
        return "muon_s2"

    return "other"
