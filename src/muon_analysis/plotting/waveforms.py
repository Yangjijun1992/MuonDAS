"""Waveform visualization and validation plots.

Aligned with the reference notebook plotting functions:
  - ``apply_lowpass_filter`` : zero-phase Butterworth low-pass.
  - ``plot_waveform`` : overlay anode & dynode for a candidate pair.
  - ``plot_by_record_id`` : time-aligned single-pair plot.
Saves figures as .png.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import numpy as np
from scipy import signal


def apply_lowpass_filter(
    waveform_array,
    cutoff_hz: float = 20e6,
    fs: float = 250e6,
    order: int = 4,
):
    """Zero-phase Butterworth low-pass filter along the time axis."""
    waveforms = np.asarray(waveform_array, dtype=float)
    is_1d = waveforms.ndim == 1
    if is_1d:
        waveforms = waveforms.reshape(1, -1)
    nyq = 0.5 * fs
    normal_cutoff = cutoff_hz / nyq
    b, a = signal.butter(order, normal_cutoff, btype="low", analog=False)
    padlen = 3 * (max(len(a), len(b)) - 1)
    if waveforms.shape[-1] <= padlen:
        return waveforms.reshape(-1) if is_1d else waveforms
    out = signal.filtfilt(b, a, waveforms, axis=-1)
    return out.reshape(-1) if is_1d else out


def _signals_for(accessor, ids):
    arr = accessor.signals(ids)
    return np.atleast_2d(np.asarray(arr, dtype=float))


def plot_pmt_comparison(
    anode_records,
    dynode_records,
    accessor,
    output_dir: str | Path,
    run_id: str,
    channel_id,
    num_samples: int = 3,
    plot_length: int = 100,
    dynode_scale: float = 110,
    sample_interval_ns: float = 4,
    lp_cutoff_hz: float | None = None,
    fs: float = 250e6,
    order: int = 4,
    plot_id: Optional[int] = None,
) -> Optional[Path]:
    """Overlay anode & dynode waveforms for candidate pairs (save .png).

    When ``lp_cutoff_hz`` is given, the dynode waveform is low-pass filtered
    (zero-phase Butterworth) before it is inverted & scaled, so the overlay
    shows the smoothed dynode signal.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if channel_id is not None:
        mask_a = anode_records["channel"] == channel_id
        mask_d = dynode_records["channel"] == channel_id
        ano = anode_records[mask_a]
        dyn = dynode_records[mask_d]
    else:
        ano = anode_records
        dyn = dynode_records

    count = min(len(ano), len(dyn), num_samples)
    if count == 0:
        return None

    ano = ano[:count]
    dyn = dyn[:count]

    waves_a = _signals_for(accessor, ano["record_id"])
    waves_d = _signals_for(accessor, dyn["record_id"])

    plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    ch_part = f"_ch{channel_id}" if channel_id is not None else ""
    id_part = f"_{plot_id}" if plot_id is not None else ""
    filename = f"compare_run_{run_id}{ch_part}{id_part}.png"
    path = plot_dir / filename

    fig, axes = plt.subplots(count, 1, figsize=(14, 4 * count), sharex=False)
    if count == 1:
        axes = [axes]

    for i in range(count):
        ax = axes[i]
        sig_a = np.asarray(waves_a[i][:plot_length], dtype=float)
        sig_d = np.asarray(waves_d[i][:plot_length], dtype=float)
        if lp_cutoff_hz is not None:
            sig_d = apply_lowpass_filter(sig_d, cutoff_hz=lp_cutoff_hz,
                                         fs=fs, order=order)
        sig_d = sig_d * -dynode_scale
        t_a = ano[i]["time"] + np.arange(len(sig_a)) * sample_interval_ns
        t_d = dyn[i]["time"] + np.arange(len(sig_d)) * sample_interval_ns
        ax.plot(t_a, sig_a, color="royalblue", alpha=0.8,
                label=f"Anode ID {ano[i]['record_id']}")
        dyn_label = (f"Dynode LP@{lp_cutoff_hz/1e6:.0f}MHz x{dynode_scale}"
                     if lp_cutoff_hz is not None
                     else f"Dynode x{dynode_scale}")
        ax.plot(t_d, sig_d, color="crimson", alpha=0.8, label=dyn_label)
        ax.axhline(0, color="black", linestyle="--", alpha=0.3)
        ax.set_ylabel("Amplitude [ADC]")
        ax.set_xlabel("Time [ns]")
        ax.legend(loc="best", fontsize=9)
        ax.grid(True, alpha=0.2)

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def plot_by_record_id(
    anode_records,
    dynode_records,
    accessor,
    record_id: int,
    output_dir: str | Path,
    run_id: str,
    plot_len: int = 100,
    sample_interval_ns: float = 4.0,
    dynode_scale: float = 110,
    cutoff_hz: float = 20e6,
    fs: float = 250e6,
    order: int = 4,
) -> Optional[Path]:
    """Time-aligned plot of a single anode/dynode pair by anode record_id."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    ano = anode_records[anode_records["record_id"] == record_id]
    if len(ano) == 0:
        return None
    rec_ano = ano[0]
    dyn_ch = dynode_records[dynode_records["channel"] == rec_ano["channel"]]
    if len(dyn_ch) == 0:
        return None
    rec_dyn = dyn_ch[np.argmin(np.abs(dyn_ch["time"] - rec_ano["time"]))]

    sig_a = _signals_for(accessor, [rec_ano["record_id"]]).reshape(-1)
    sig_d = _signals_for(accessor, [rec_dyn["record_id"]]).reshape(-1)
    sig_d = apply_lowpass_filter(sig_d, cutoff_hz, fs, order) * -dynode_scale

    shift_bins = int(round((rec_dyn["time"] - rec_ano["time"]) / sample_interval_ns))
    aligned_len = max(len(sig_a), len(sig_d) + abs(shift_bins), plot_len)
    a_al = np.zeros(aligned_len)
    d_al = np.zeros(aligned_len)
    a_al[: len(sig_a)] = sig_a
    d_start = max(0, shift_bins)
    s_start = max(0, -shift_bins)
    copy_len = min(len(sig_d) - s_start, aligned_len - d_start)
    if copy_len > 0:
        d_al[d_start:d_start + copy_len] = sig_d[s_start:s_start + copy_len]

    plot_len2 = min(plot_len, aligned_len)
    x = np.arange(plot_len2) * sample_interval_ns
    path = Path(output_dir) / f"byid_run_{run_id}_id{record_id}.png"

    plt.figure(figsize=(14, 6))
    plt.plot(x, a_al[:plot_len2], color="royalblue", alpha=0.85,
             label=f"Anode ID {rec_ano['record_id']}")
    plt.plot(x, d_al[:plot_len2], color="crimson", alpha=0.85,
             label=f"Dynode filtered x{dynode_scale} ID {rec_dyn['record_id']}")
    plt.axhline(0, color="gray", linestyle="--", alpha=0.5)
    plt.xlabel("Time [ns]")
    plt.ylabel("Amplitude [ADC]")
    plt.title(f"Waveform (time aligned) ch={rec_ano['channel']} shift={shift_bins}")
    plt.legend(loc="best")
    plt.grid(True, alpha=0.2)
    plt.tight_layout()
    plt.savefig(path, dpi=120)
    plt.close()
    return path


def plot_peak_pairs(peak, run_data, output_dir, run_id, sample_interval_ns=4.0,
                    dynode_scale=110, lp_cutoff_hz=None, fs=250e6,
                    plot_len=200) -> list[Path]:
    """Per-channel pair plots for a peak: one subplot per unique channel showing
    that channel's anode waveform(s) (raw, negative polarity) and dynode
    waveform(s) (low-pass filtered when lp_cutoff_hz given, then inverted x -dynode_scale).
    Time axis in ns relative to each record's start time (record['time'] + k*sample_interval_ns).
    Saved as peak{peaks_id:03d}_pairs_run_{run_id}.png. Returns saved paths
    (empty list if the peak has no records). matplotlib Agg backend."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from muon_analysis.filtering import SignalAccessor

    if not peak.anode_records and not peak.dynode_records:
        return []

    accessor = SignalAccessor.from_run_data(run_data)
    plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    path = plot_dir / f"peak{peak.peaks_id:03d}_pairs_run_{run_id}.png"

    channels = sorted({r.channel for r in peak.anode_records} |
                      {r.channel for r in peak.dynode_records})
    fig, axes = plt.subplots(len(channels), 1, figsize=(14, 4 * len(channels)),
                             sharex=False)
    if len(channels) == 1:
        axes = [axes]

    for i, ch in enumerate(channels):
        ax = axes[i]
        for rec in peak.anode_records:
            if rec.channel != ch:
                continue
            sig = np.asarray(accessor.signals([rec.record_id]).reshape(-1)[:plot_len],
                             dtype=float)
            t = rec.time_ns + np.arange(len(sig)) * sample_interval_ns
            ax.plot(t, sig, color="royalblue", alpha=0.8,
                    label=f"Anode ID {rec.record_id}")
        for rec in peak.dynode_records:
            if rec.channel != ch:
                continue
            sig = np.asarray(accessor.signals([rec.record_id]).reshape(-1)[:plot_len],
                             dtype=float)
            if lp_cutoff_hz is not None:
                sig = apply_lowpass_filter(sig, cutoff_hz=lp_cutoff_hz, fs=fs)
            sig = sig * -dynode_scale
            t = rec.time_ns + np.arange(len(sig)) * sample_interval_ns
            dyn_label = (f"Dynode LP@{lp_cutoff_hz/1e6:.0f}MHz x{dynode_scale}"
                         if lp_cutoff_hz is not None else f"Dynode x{dynode_scale}")
            ax.plot(t, sig, color="crimson", alpha=0.8, label=f"{dyn_label} ID {rec.record_id}")
        ax.axhline(0, color="black", linestyle="--", alpha=0.3)
        ax.set_ylabel("Amplitude [ADC]")
        ax.set_xlabel("Time [ns]")
        ax.set_title(f"Peak {peak.peaks_id} ch={ch}")
        ax.legend(loc="best", fontsize=9)
        ax.grid(True, alpha=0.2)

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return [path]


def plot_peak_overlay(peak, run_data, output_dir, run_id, sample_interval_ns=4.0,
                      dynode_scale=110, lp_cutoff_hz=None, fs=250e6,
                      plot_len=200) -> list[Path]:
    """Two stacked panels for a peak:
      panel 1: ALL anode waveforms overlaid (time-aligned to their own record start);
      panel 2: ALL dynode waveforms overlaid (LP + inverted x dynode_scale).
    Saved as peak{peaks_id:03d}_overlay_run_{run_id}.png. Returns saved paths."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from muon_analysis.filtering import SignalAccessor

    if not peak.anode_records and not peak.dynode_records:
        return []

    accessor = SignalAccessor.from_run_data(run_data)
    plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    path = plot_dir / f"peak{peak.peaks_id:03d}_overlay_run_{run_id}.png"

    fig, (ax_a, ax_d) = plt.subplots(2, 1, figsize=(14, 8), sharex=False)

    for rec in peak.anode_records:
        sig = np.asarray(accessor.signals([rec.record_id]).reshape(-1)[:plot_len],
                         dtype=float)
        t = rec.time_ns + np.arange(len(sig)) * sample_interval_ns
        ax_a.plot(t, sig, color="royalblue", alpha=0.8, label=f"Anode ID {rec.record_id}")
    ax_a.axhline(0, color="black", linestyle="--", alpha=0.3)
    ax_a.set_ylabel("Amplitude [ADC]")
    ax_a.set_title(f"Peak {peak.peaks_id} Anode overlay")
    ax_a.legend(loc="best", fontsize=9)
    ax_a.grid(True, alpha=0.2)

    for rec in peak.dynode_records:
        sig = np.asarray(accessor.signals([rec.record_id]).reshape(-1)[:plot_len],
                         dtype=float)
        if lp_cutoff_hz is not None:
            sig = apply_lowpass_filter(sig, cutoff_hz=lp_cutoff_hz, fs=fs)
        sig = sig * -dynode_scale
        t = rec.time_ns + np.arange(len(sig)) * sample_interval_ns
        ax_d.plot(t, sig, color="crimson", alpha=0.8, label=f"Dynode ID {rec.record_id}")
    ax_d.axhline(0, color="black", linestyle="--", alpha=0.3)
    ax_d.set_ylabel("Amplitude [ADC]")
    ax_d.set_xlabel("Time [ns]")
    ax_d.set_title(f"Peak {peak.peaks_id} Dynode overlay")
    ax_d.legend(loc="best", fontsize=9)
    ax_d.grid(True, alpha=0.2)

    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return [path]
