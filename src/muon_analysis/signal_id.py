"""Peak-level signal discrimination (width-cut based).

Classification (checked in order):

  - ``"muon_s1"``: a narrow, prompt-like peak -- **both** cuts satisfied:
    ``width_20_50area < w20_50area_max_ns`` (default 100 ns) **and**
    ``width_90area < w90area_max_ns`` (default 1000 ns).
  - ``"muon_s2"``: a wide, delayed-like peak -- exceeds either S1 cut
    (the complement of the S1 selection).
  - ``"other"``: peaks excluded by an optional gate (``long_wave_min_samples``
    or ``n_channels``); when neither gate is configured every peak is
    ``muon_s1`` or ``muon_s2``.

The earlier ``end_first``-based ``muon_s1_width`` / ``muon_s2_width`` criteria
are **void**: a muon tail keeps the summed waveform below the baseline-return
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
    """Return the signal type of a peak (``muon_s1`` / ``muon_s2`` / ``other``)."""
    cfg = (config or {}).get("signal_id", {}) or {}

    long_min = cfg.get("long_wave_min_samples")
    if long_min is not None and peak_features.wave_len_samples <= int(long_min):
        return "other"

    s1 = cfg.get("muon_s1", {}) or {}
    n_ch_s1 = s1.get("n_channels")
    if n_ch_s1 is not None and n_channels != int(n_ch_s1):
        return "other"
    if peak_features.width_20_50area < float(s1.get("w20_50area_max_ns", 100.0)) \
            and peak_features.width_90area < float(s1.get("w90area_max_ns", 1000.0)):
        return "muon_s1"

    s2 = cfg.get("muon_s2", {}) or {}
    n_ch_s2 = s2.get("n_channels")
    if n_ch_s2 is not None and n_channels != int(n_ch_s2):
        return "other"
    return "muon_s2"
