"""Peak-level signal discrimination (S1/S2 width based).

For peaks whose aligned sum waveform is long (``wave_len_samples`` >
``long_wave_min_samples``, default 20000 samples = 80 us), the waveform is
decomposed into:

  - a **prompt** component (S1): ``start`` -> ``end_first`` (first return to
    baseline)  ->  ``muon_s1_width_ns``
  - a **delayed** component (S2): ``end_first`` -> ``end_final`` (last return
    to baseline)  ->  ``muon_s2_width_ns``

Classification (checked in order):

  - ``"muon_s2"``: 7-PMT coincidence with a significant delayed component
    (``muon_s2_width_ns >= s2_width_min_ns``).
  - ``"muon_s1"``: 7-PMT coincidence with a prompt component whose width is
    within ``[s1_width_min_ns, s1_width_max_ns]`` and ``height >= height_min``.
  - ``"other"``: everything else.

Thresholds are configurable under ``config["signal_id"]``.
"""

from __future__ import annotations

from typing import Any, Dict

from muon_analysis.models import PeakFeatures


def classify_signal(
    peak_features: PeakFeatures,
    n_channels: int,
    config: Dict[str, Any],
) -> str:
    """Return the signal type of a peak (``muon_s1`` / ``muon_s2`` / ``other``)."""
    cfg = (config or {}).get("signal_id", {}) or {}
    long_min = int(cfg.get("long_wave_min_samples", 20000))

    if peak_features.wave_len_samples <= long_min:
        return "other"

    s2 = cfg.get("muon_s2", {}) or {}
    if n_channels == int(s2.get("n_channels", 7)) \
            and peak_features.muon_s2_width_ns >= float(s2.get("s2_width_min_ns", 500.0)):
        return "muon_s2"

    s1 = cfg.get("muon_s1", {}) or {}
    if n_channels == int(s1.get("n_channels", 7)) \
            and float(s1.get("s1_width_min_ns", 0.0)) <= peak_features.muon_s1_width_ns <= float(s1.get("s1_width_max_ns", 500.0)) \
            and peak_features.height >= float(s1.get("height_min", 4000.0)):
        return "muon_s1"

    return "other"
