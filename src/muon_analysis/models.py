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
    anode_area_pe_per_pmt: Dict[str, float] = field(default_factory=dict)  # pmt_id -> per-channel anode integral scaled to PE (own gain)
    dynode_area_pe_per_pmt: Dict[str, float] = field(default_factory=dict) # pmt_id -> per-channel dynode integral scaled to PE (own gain)
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
    width: float = 0.0         # summed-waveform pulse span (start -> final end) [ns]
    rise_time: float = 0.0     # summed-waveform rise (start->peak) [ns]
    width_90area: float = 0.0  # max over channels: width from start containing 90% area [ns]
    width_50area: float = 0.0  # max over channels: width from start containing 50% area [ns]
    width_20_50area: float = 0.0  # anode_sum: area-accumulation width between 20% and 50% [ns]
    n_samples_gt1000adc: int = 0  # anode_sum: #samples with |amplitude| > 1000 ADC
    end_first_sample: int = 0     # pulse-finder end (first return to baseline)
    end_final_sample: int = 0     # whole peak waveform final end (last significant sample)
    # muon S1 / S2 decomposition: S1 = [a_st, s1_end], S2 = [s1_end, end_final],
    # where s1_end is the S1/S2 cut point found by find_s1_endpoint_from_peak.
    muon_s1_start_sample: int = 0   # = a_st (anode sum start)
    muon_s1_end_sample: int = 0     # = s1_end (S1 end == S2 start)
    muon_s2_end_sample: int = 0     # = end_final
    muon_s1_width_ns: float = 0.0   # (s1_end - a_st) * 4
    muon_s2_width_ns: float = 0.0   # (end_final - s1_end) * 4
    muon_s1_height_an: float = 0.0  # max |anode_sum| in S1 window
    muon_s2_height_an: float = 0.0  # max |anode_sum| in S2 window
    muon_s1_height_dy: float = 0.0  # max |dynode_sum| in S1 window
    muon_s2_height_dy: float = 0.0  # max |dynode_sum| in S2 window
    muon_s1_area_an: float = 0.0   # anode_sum integral over S1 window, PE
    muon_s1_area_dy: float = 0.0   # dynode_sum integral over S1 window, PE
    muon_s2_area_an: float = 0.0   # anode_sum integral over S2 window, PE
    muon_s2_area_dy: float = 0.0   # dynode_sum integral over S2 window, PE
    wave_len_samples: int = 0     # length of the peak sum waveform [samples]
    # aligned (by pulse start) summed waveforms over all channels, in npz only
    anode_sum: Optional[np.ndarray] = field(default=None, repr=False)
    dynode_sum: Optional[np.ndarray] = field(default=None, repr=False)
    sum_ref: int = 50  # alignment reference (samples) used for the sums
    # side-specific area of the summed waveforms (full waveform, scaled to PE)
    anode_sum_area: float = 0.0
    dynode_sum_area: float = 0.0
    signal_type: str = "other"  # peak-level discrimination label ("S1" / "S2" / "other")

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
            "width_90area": self.width_90area,
            "width_50area": self.width_50area,
            "width_20_50area": self.width_20_50area,
            "n_samples_gt1000adc": self.n_samples_gt1000adc,
            "end_first_sample": self.end_first_sample,
            "end_final_sample": self.end_final_sample,
            "muon_s1_start_sample": self.muon_s1_start_sample,
            "muon_s1_end_sample": self.muon_s1_end_sample,
            "muon_s2_end_sample": self.muon_s2_end_sample,
            "muon_s1_width_ns": self.muon_s1_width_ns,
            "muon_s2_width_ns": self.muon_s2_width_ns,
            "muon_s1_height_an": self.muon_s1_height_an,
            "muon_s2_height_an": self.muon_s2_height_an,
            "muon_s1_height_dy": self.muon_s1_height_dy,
            "muon_s2_height_dy": self.muon_s2_height_dy,
            "muon_s1_area_an": self.muon_s1_area_an,
            "muon_s1_area_dy": self.muon_s1_area_dy,
            "muon_s2_area_an": self.muon_s2_area_an,
            "muon_s2_area_dy": self.muon_s2_area_dy,
            "wave_len_samples": self.wave_len_samples,
            "anode_sum_area": self.anode_sum_area,
            "dynode_sum_area": self.dynode_sum_area,
            "signal_type": self.signal_type,
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
