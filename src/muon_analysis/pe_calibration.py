"""Charge -> photoelectron (PE) conversion and reference integration logic.

Reference calibration (from the example notebook):

    pe_fact = (2. / 16384) * 4.e-9 / (50 * 1.6e-19) / 1.e6
    pe_calibration(channel) = pe_fact / gain(channel)
"""

from __future__ import annotations

import numpy as np

from muon_analysis.features import build_window_resolver, integrate_area
from muon_analysis.gain import GainDB


def pe_fact() -> float:
    """Dimensionless ADC -> charge conversion factor (reference constant)."""
    return (2.0 / 16384.0) * 4.0e-9 / (50.0 * 1.6e-19) / 1.0e6


def pe_calibration(gain: float) -> float:
    """Return PE calibration factor for a given SPE gain."""
    if gain == 0:
        raise ZeroDivisionError("gain is zero; cannot calibrate to PE")
    return pe_fact() / gain


def charge_to_pe(charge: float, gain: float) -> float:
    """Convert an integrated charge to photoelectron count."""
    return charge * pe_calibration(gain)


def compute_integral_pe(
    signals: np.ndarray,
    channel_ids,
    gain_db: GainDB,
    signal_polarity: str = "positive",
    config: dict | None = None,
    area_field: str = "area_pe",
) -> np.ndarray:
    """Integrate waveforms over the configured window and scale to PE.

    ``signals`` has shape ``(N, T)``; per-row ``channel_id`` selects the gain.
    Mirrors the reference ``compute_integral_pe``.
    """
    resolver = build_window_resolver(config or {})
    calibs = np.asarray(
        [pe_calibration(gain_db.get_gain(int(ch))) for ch in channel_ids],
        dtype=np.float32,
    )
    n, t = np.asarray(signals).shape
    results = np.zeros(n, dtype=np.float32)
    for i in range(n):
        area = integrate_area(
            signals[i], resolver, signal_polarity=signal_polarity,
            baseline=None,
        )
        results[i] = area * calibs[i]
    return results


def compute_raw_segment_pe(
    signals: np.ndarray,
    channel_ids,
    gain_db: GainDB,
    signal_polarity: str = "positive",
) -> np.ndarray:
    """Integrate the whole waveform segment and scale to PE (seg_area_pe)."""
    calibs = np.asarray(
        [pe_calibration(gain_db.get_gain(int(ch))) for ch in channel_ids],
        dtype=np.float32,
    )
    signals = np.asarray(signals)
    if signal_polarity == "negative":
        raw_area = np.sum(np.abs(signals), axis=1)
    else:
        raw_area = np.sum(signals, axis=1)
    return (raw_area * calibs).astype(np.float32)
