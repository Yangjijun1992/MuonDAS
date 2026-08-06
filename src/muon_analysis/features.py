"""Waveform feature computation and integration-window strategy.

Charge (area) integration strategy:
  - ``FixedWindowResolver``: integrate over a fixed / given ``[start, end)``
    range (aligned with the reference ``compute_integral_pe``).
  - ``PeakFinderWindowResolver``: reserved plug-in point — a peak-finding
    algorithm (to be supplied later by the user) determines the waveform
    starting point, from which the integration range is derived.

Both implement :class:`IntegrationWindowResolver` so downstream callers are
agnostic to the chosen strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

import numpy as np


class IntegrationWindowResolver(ABC):
    """Resolve the integration range ``(start, end)`` for a waveform."""

    @abstractmethod
    def resolve(self, waveform: np.ndarray, **kwargs) -> Tuple[int, int]:
        """Return ``(start, end)`` indices for the integration window."""
        raise NotImplementedError


@dataclass
class FixedWindowResolver(IntegrationWindowResolver):
    """Fixed / given integration window ``[start, end)``."""

    start: int
    end: int

    def resolve(self, waveform: np.ndarray, **kwargs) -> Tuple[int, int]:
        n = waveform.shape[-1]
        end = min(int(self.end), n)
        start = min(int(self.start), end)
        return start, end


class PeakFinderWindowResolver(IntegrationWindowResolver):
    """Reserved plug-in for peak-finding based integration start.

    TODO: user will supply a peak/signal-start finding algorithm.  Currently
    it falls back to a fixed window so the pipeline remains runnable.
    """

    def __init__(self, fallback: FixedWindowResolver, peak_finder=None):
        self.fallback = fallback
        self.peak_finder = peak_finder

    def resolve(self, waveform: np.ndarray, **kwargs) -> Tuple[int, int]:
        if self.peak_finder is not None:
            start = int(self.peak_finder(waveform, **kwargs))
            _, end = self.fallback.resolve(waveform, **kwargs)
            return start, end
        return self.fallback.resolve(waveform, **kwargs)


def build_window_resolver(config: Dict[str, Any]) -> IntegrationWindowResolver:
    """Construct the configured integration window resolver."""
    features_cfg = config.get("features", {})
    mode = features_cfg.get("integral_window_mode", "fixed")
    start = int(features_cfg.get("integral_start", 20))
    end = int(features_cfg.get("integral_end", 100))
    fixed = FixedWindowResolver(start=start, end=end)
    if mode == "peak_finder":
        return PeakFinderWindowResolver(fallback=fixed)
    return fixed


def integrate_area(
    waveform: np.ndarray,
    resolver: IntegrationWindowResolver,
    signal_polarity: str = "positive",
    baseline: Optional[float] = None,
) -> float:
    """Integrate ``waveform`` over the window resolved by ``resolver``.

    Positive pulses are summed as-is; negative pulses are summed in absolute
    value (aligned with the reference behaviour).
    """
    if baseline is not None:
        waveform = waveform - baseline
    start, end = resolver.resolve(np.asarray(waveform))
    if signal_polarity == "negative":
        return float(np.sum(np.abs(waveform[start:end])))
    return float(np.sum(waveform[start:end]))


def compute_baseline(waveform: np.ndarray, baseline_samples: int = 10) -> float:
    """Mean of the first ``baseline_samples`` samples."""
    return float(np.mean(waveform[:baseline_samples]))


@dataclass
class Features:
    """Feature vector for a single waveform."""

    height: float
    charge: float
    rise_time: float
    width: float
    baseline: float

    def as_dict(self) -> Dict[str, float]:
        return {
            "height": self.height,
            "charge": self.charge,
            "rise_time": self.rise_time,
            "width": self.width,
            "baseline": self.baseline,
        }


def _crossing(waveform: np.ndarray, frac: float, peak_index: int, baseline: float,
              peak_amp: float, direction: int) -> Optional[float]:
    """Find index where amplitude crosses ``frac`` of peak on path to peak."""
    target = baseline + direction * frac * abs(peak_amp - baseline)
    indices = np.arange(len(waveform))
    if direction > 0:
        seg = indices[: peak_index + 1]
    else:
        seg = indices[peak_index:]
    if len(seg) < 2:
        return None
    vals = waveform[seg]
    cross = np.argwhere((vals - target) * direction >= 0)
    if len(cross) == 0:
        return None
    return int(seg[cross[0][0]])

def _fwhm_samples(waveform: np.ndarray, peak_index: int, baseline: float,
                  peak_amp: float, direction: int) -> Optional[float]:
    """Number of samples above the half-maximum level (FWHM in samples)."""
    above = (waveform - baseline) * direction >= 0.5 * abs(peak_amp - baseline)
    if not np.any(above):
        return None
    return float(np.count_nonzero(above))


def compute_features(
    waveform: np.ndarray,
    signal_polarity: str = "positive",
    baseline_samples: int = 10,
    rise_low: float = 0.1,
    rise_high: float = 0.9,
    window: Optional[Tuple[int, int]] = None,
) -> tuple:
    """Compute height, charge, rise_time, width, baseline for a waveform.

    Returns a tuple ``(features: Features, peak_index: int)``.
    """
    wf = np.asarray(waveform, dtype=float)
    baseline = compute_baseline(wf, baseline_samples)
    direction = 1 if signal_polarity == "positive" else -1
    centred = (wf - baseline) * direction
    peak_index = int(np.argmax(centred))
    peak_amp = wf[peak_index]

    if window is not None:
        charge = integrate_area(wf, FixedWindowResolver(window[0], window[1]),
                                signal_polarity=signal_polarity)
    else:
        charge = float(np.sum(centred)) if signal_polarity == "positive" else float(np.sum(np.abs(wf - baseline)))

    height = abs(peak_amp - baseline)

    low_idx = _crossing(wf, rise_low, peak_index, baseline, peak_amp, direction)
    high_idx = _crossing(wf, rise_high, peak_index, baseline, peak_amp, direction)
    if low_idx is not None and high_idx is not None and high_idx > low_idx:
        rise_time = float(high_idx - low_idx)
    else:
        rise_time = float("nan")

    width = _fwhm_samples(wf, peak_index, baseline, peak_amp, direction)
    if width is None:
        width = float("nan")

    feats = Features(
        height=float(height),
        charge=float(charge),
        rise_time=rise_time,
        width=width,
        baseline=baseline,
    )
    return feats, peak_index
