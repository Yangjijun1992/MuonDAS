"""Core data models used across the analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


@dataclass
class PeakRecord:
    """A single waveform record belonging to a peak.

    ``record_id`` is the raw record identifier from the records table (also
    the value used by the ``SignalAccessor``); ``time_ns`` is the record's
    start time; ``is_dynode`` distinguishes dynode (True) from anode (False).

    ``pulse_start_sample`` / ``pulse_end_sample`` hold this record's own
    pulse boundaries (sample indices, from :func:`pulse_finder`); None when
    no pulse was found for the channel.
    """

    record_id: int
    channel: int
    time_ns: float
    is_dynode: bool
    pulse_start_sample: Optional[int] = None
    pulse_end_sample: Optional[int] = None

    @property
    def has_pulse(self) -> bool:
        return self.pulse_start_sample is not None and self.pulse_end_sample is not None


@dataclass
class Peak:
    """A cluster of matched anode/dynode waveforms within a time window.

    Produced by :func:`muon_analysis.clustering.cluster_peaks`: all matched
    records whose record time lies within ``clustering.window_ns`` of the
    cluster anchor are grouped into a single ``Peak`` (possibly spanning
    several anode channels and several dynode channels).
    """

    peaks_id: int
    start_time_ns: float
    end_time_ns: float
    anode_records: List[PeakRecord] = field(default_factory=list)
    dynode_records: List[PeakRecord] = field(default_factory=list)
    # Row indices into the ``match_df`` DataFrame whose pairs belong to this peak.
    match_rows: List[int] = field(default_factory=list)
    # Sorted unique channel numbers across all member records.
    channels: List[int] = field(default_factory=list)

    @property
    def n_anode(self) -> int:
        return len(self.anode_records)

    @property
    def n_dynode(self) -> int:
        return len(self.dynode_records)

    @property
    def n_channels(self) -> int:
        return len(self.channels)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "peaks_id": self.peaks_id,
            "start_time_ns": self.start_time_ns,
            "end_time_ns": self.end_time_ns,
            "anode_record_ids": [r.record_id for r in self.anode_records],
            "dynode_record_ids": [r.record_id for r in self.dynode_records],
            "channels": list(self.channels),
            "match_rows": list(self.match_rows),
        }


@dataclass
class PeakFeatures:
    """Feature summary for a single :class:`Peak`.

    Per-record features are stored keyed by ``record_id``; dynode-side
    features are computed **after** the low-pass filter and ``×dynode_scale``
    amplification (both height and area scaled).  ``charge_per_pmt`` maps
    ``pmt_id`` -> charge weight for the COG reconstruction (the side is
    selected by ``cog.charge_source``).
    """

    peaks_id: int
    time_ns: float
    channels: List[int]
    anode_record_ids: List[int]
    dynode_record_ids: List[int]
    anode_features: Dict[int, Any] = field(default_factory=dict)   # record_id -> Features
    dynode_features: Dict[int, Any] = field(default_factory=dict)  # record_id -> Features
    anode_pe: Dict[int, float] = field(default_factory=dict)       # record_id -> PE
    dynode_pe: Dict[int, float] = field(default_factory=dict)      # record_id -> PE
    charge_per_pmt: Dict[str, float] = field(default_factory=dict) # pmt_id -> charge weight
    anode_area_per_pmt: Dict[str, float] = field(default_factory=dict)  # pmt_id -> per-channel (pre-sum) raw anode integral
    dynode_area_per_pmt: Dict[str, float] = field(default_factory=dict) # pmt_id -> per-channel (pre-sum, x1) dynode integral
    anode_area_pe: float = 0.0
    dynode_area_pe: float = 0.0
    # anode saturation reconstruction: when an anode channel clips at the ADC
    # floor its true charge is taken from the (linear) dynode channel x
    # dynode_scale; these are the per-channel-reconstructed totals.
    anode_area_pe_recon: float = 0.0
    n_anode_saturated: int = 0
    anode_saturation_frac: float = 0.0
    area_ano: float = 0.0      # total charge from all anode channels (uncalibrated)
    area_dyn: float = 0.0      # total charge from all dynode channels (x dynode_scale)
    # shape params computed on the summed waveforms (anode reference)
    height: float = 0.0        # summed-waveform height
    width: float = 0.0         # summed-waveform FWHM [ns]
    rise_time: float = 0.0     # summed-waveform rise (start->peak) [ns]
    width_ns: float = 0.0      # summed-waveform pulse duration (end-start) [ns]
    width_90area: float = 0.0  # max over channels: width from start containing 90% area [ns]
    width_50area: float = 0.0  # max over channels: width from start containing 50% area [ns]
    # aligned (by pulse start) summed waveforms over all channels, in npz only
    anode_sum: Optional[np.ndarray] = field(default=None, repr=False)
    dynode_sum: Optional[np.ndarray] = field(default=None, repr=False)
    sum_ref: int = 50  # alignment reference (samples) used for the sums
    # side-specific area of the summed waveforms (full waveform, scaled to PE)
    anode_sum_area: float = 0.0
    dynode_sum_area: float = 0.0

    def as_dict(self) -> Dict[str, Any]:
        return {
            "peaks_id": self.peaks_id,
            "time_ns": self.time_ns,
            "channels": list(self.channels),
            "anode_record_ids": list(self.anode_record_ids),
            "dynode_record_ids": list(self.dynode_record_ids),
            "anode_area_pe": self.anode_area_pe,
            "dynode_area_pe": self.dynode_area_pe,
            "area_ano": self.area_ano,
            "area_dyn": self.area_dyn,
            "height": self.height,
            "width": self.width,
            "rise_time": self.rise_time,
            "width_ns": self.width_ns,
            "width_90area": self.width_90area,
            "width_50area": self.width_50area,
            "anode_sum_area": self.anode_sum_area,
            "dynode_sum_area": self.dynode_sum_area,
            "charge_per_pmt": dict(self.charge_per_pmt),
        }


@dataclass
class MuonCandidate:
    """A peak that passed the muon candidate selection."""

    peaks_id: int
    features: PeakFeatures
    start_time_ns: float
    end_time_ns: float
    passed_conditions: Dict[str, bool] = field(default_factory=dict)

    @property
    def channels(self) -> List[int]:
        return self.features.channels


@dataclass
class RunInfo:
    """Metadata describing a single run.

    Mirrors the ``pmt_analysis.models.RunInfo`` shape used by the reference
    example scripts so their logic (raw_reader, runinfo) can be reused.
    """

    run_id: str
    runtype: str
    run_dir: Path
    runinfo_path: Path
    raw_dir: Path
    outfile_name: str = ""
    source: str = ""
    datatype: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def pmt_id_map(self) -> Dict[tuple, str]:
        """Mapping ``(board_id, channel) -> pmt_id`` from runinfo 'mapping'."""
        result: Dict[tuple, str] = {}
        raw_mapping = self.metadata.get("mapping")
        if not raw_mapping:
            return result
        for board_info in raw_mapping:
            board_id = board_info.get("board_id")
            for ch_info in board_info.get("channels", []):
                result[(board_id, ch_info.get("ch"))] = ch_info.get("pmt")
        return result
