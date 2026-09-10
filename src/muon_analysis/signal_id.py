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
    """Return the signal type of a peak (``"muon_s1"`` or ``"other"``).

    ``muon_s1`` requires ALL of (AND):

      - ``n_channels == n_channels`` (default 7, full 7-PMT coincidence)
      - ``width_20_50area < width_20_50area_max`` (default 80 ns)
      - ``anode_sum_area > anode_sum_area_min`` (default 300 PE)
      - ``height >= height_min`` (default 4000 ADC)
      - ``width_90area < width_90area_max`` (default 500 ns)
    """
    cfg = (config or {}).get("signal_id", {}).get("muon_s1", {}) or {}
    if n_channels != int(cfg.get("n_channels", 7)):
        return "other"
    if not (peak_features.width_20_50area < float(cfg.get("width_20_50area_max", 80.0))):
        return "other"
    if not (peak_features.anode_sum_area > float(cfg.get("anode_sum_area_min", 300.0))):
        return "other"
    if not (peak_features.height >= float(cfg.get("height_min", 4000.0))):
        return "other"
    if not (peak_features.width_90area < float(cfg.get("width_90area_max", 500.0))):
        return "other"
    return "muon_s1"
