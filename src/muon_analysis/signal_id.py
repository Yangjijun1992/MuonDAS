"""Peak-level signal discrimination (width-cut based).

Classification (checked in order):

  - ``"S1"``: a narrow, prompt-like peak -- **both** cuts satisfied:
    ``width_20_50area < w20_50area_max_ns`` (default 100 ns) **and**
    ``width_90area < w90area_max_ns`` (default 1000 ns).
  - ``"S2"``: a wide, delayed-like peak -- exceeds either S1 cut
    (the complement of the S1 selection).
  - ``"other"``: peaks excluded by an optional gate (``long_wave_min_samples``
    or ``n_channels``); when neither gate is configured every peak is
    ``S1`` or ``S2``.

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
    n_ch_s1 = s1.get("n_channels")
    if n_ch_s1 is not None and n_channels != int(n_ch_s1):
        return "other"
    if peak_features.width_20_50area < float(s1.get("w20_50area_max_ns", 100.0)) \
            and peak_features.width_90area < float(s1.get("w90area_max_ns", 1000.0)):
        return "S1"

    s2 = cfg.get("s2", {}) or {}
    n_ch_s2 = s2.get("n_channels")
    if n_ch_s2 is not None and n_channels != int(n_ch_s2):
        return "other"
    return "S2"
