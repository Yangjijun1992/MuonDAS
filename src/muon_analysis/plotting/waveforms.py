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


def _fetch(accessor, record_id, plot_len):
    """Waveform slice ([:plot_len]) for a record, as float 1-D."""
    return np.asarray(accessor.signals([record_id]).reshape(-1)[:plot_len],
                      dtype=float)


def _time_axis(rec, n_samples, sample_interval_ns):
    return rec.time_ns + np.arange(n_samples) * sample_interval_ns


def _mark_window(ax, peak, color="green"):
    """Vertical lines at the peak clustering window (start/end time)."""
    ax.axvline(peak.start_time_ns, color=color, linestyle="--", alpha=0.7,
               linewidth=1.2, label=f"peak start {peak.start_time_ns:.0f}ns")
    ax.axvline(peak.end_time_ns, color=color, linestyle=":", alpha=0.7,
               linewidth=1.2, label=f"peak end {peak.end_time_ns:.0f}ns")


def plot_peak_verification(peak, run_data, output_dir, run_id,
                           sample_interval_ns=4.0, dynode_scale=110,
                           lp_cutoff_hz=None, fs=250e6, plot_len=1500,
                           adaptive=True, margin_ns=60.0,
                           end_consecutive=3, show_window=True,
                           mark_rise=True) -> list[Path]:
    """Three verification figures for a peak, clustering window marked.

    Figure 1 (anode):   all anode waveforms overlaid + per-channel panels.
    Figure 2 (dynode):  all dynode waveforms overlaid (LP + inverted x scale)
                        + per-channel panels.
    Figure 3 (compare): anode overlay vs dynode overlay (LP + inverted x
                        scale, unified polarity) in one panel.

    Vertical lines mark the peak start/end time and each channel's own pulse
    window (orange).  When ``mark_rise`` (default) the anode rise edge is
    marked too: 10% crossing (magenta) and 90% crossing (cyan) dashed lines,
    so the rise-time width can be checked at a glance.  When ``adaptive``
    (default) each figure's time axis is zoomed to its own channels' pulse
    region (``[min pulse_start - margin, max valid pulse_end + margin]``,
    capped by the raw record lengths; a record-end fallback end does not
    stretch the window).  The compare figure uses the dynode-side window
    (dynode records are the shortest, so the pulse-aligned comparison stays
    legible even when anode records are much longer).  Otherwise the first
    ``plot_len`` samples are shown.
    Returns up to three saved PNG paths. matplotlib Agg backend.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from muon_analysis.filtering import SignalAccessor
    from muon_analysis.features import pulse_peak_index

    accessor = SignalAccessor.from_run_data(run_data)
    plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    prefix = f"peak{peak.peaks_id:03d}_verify"

    all_channels = sorted({r.channel for r in peak.anode_records} |
                          {r.channel for r in peak.dynode_records})
    cmap = plt.get_cmap("tab10")
    ch_color = {ch: cmap(i % 10) for i, ch in enumerate(all_channels)}

    def fetch(rec):
        sig = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                         dtype=float)
        return sig if adaptive else sig[:plot_len]

    def side_window(records):
        """Adaptive window over one side's records, capped by their own raw
        record lengths; record-end fallback ends do not stretch it."""
        xs: list[float] = []
        xe: list[float] = []
        starts: list[float] = []
        min_len = None
        for rec in records:
            L = len(accessor.signals([rec.record_id]).reshape(-1))
            starts.append(rec.time_ns)
            min_len = L if min_len is None else min(min_len, L)
            if rec.has_pulse and rec.pulse_end_sample < L - end_consecutive:
                xs.append(rec.time_ns + rec.pulse_start_sample * sample_interval_ns)
                xe.append(rec.time_ns + rec.pulse_end_sample * sample_interval_ns)
        if not xs:
            return None
        if not xe:
            xe.append(min(starts) + min_len * sample_interval_ns)
        return min(xs) - margin_ns, max(xe) + margin_ns

    anode_window = side_window(peak.anode_records)
    dynode_window = side_window(peak.dynode_records)

    def trace(rec):
        sig = fetch(rec)
        if rec.is_dynode:
            if lp_cutoff_hz is not None:
                sig = apply_lowpass_filter(sig, cutoff_hz=lp_cutoff_hz, fs=fs)
            sig = sig * -dynode_scale
        return sig

    def mark_rise(ax, rec, with_label):
        if not mark_rise or rec.pulse_start_sample is None:
            return  # rise span = pulse start -> pulse extremum
        sig = accessor.signals([rec.record_id]).reshape(-1)
        pk = pulse_peak_index(
            sig, signal_polarity="positive" if rec.is_dynode else "negative")
        st_t = rec.time_ns + rec.pulse_start_sample * sample_interval_ns
        pk_t = rec.time_ns + pk * sample_interval_ns
        kw = dict(linestyle="--", lw=1.0, alpha=0.8)
        if with_label:
            ax.axvline(st_t, color="magenta", label=f"rise st {st_t:.0f}ns", **kw)
            ax.axvline(pk_t, color="cyan", label=f"rise peak {pk_t:.0f}ns", **kw)
        else:
            ax.axvline(st_t, color="magenta", **kw)
            ax.axvline(pk_t, color="cyan", **kw)

    def overlay_and_channels(records, title, fname, window):
        if not records:
            return
        channels = sorted({r.channel for r in records})
        n = 1 + len(channels)
        fig, axes = plt.subplots(n, 1, figsize=(14, 3 * n), sharex=True)
        ax_overlay = axes[0]
        for rec in records:
            sig = trace(rec)
            ls = "--" if rec.is_dynode else "-"
            ax_overlay.plot(_time_axis(rec, len(sig), sample_interval_ns), sig,
                            color=ch_color[rec.channel], alpha=0.85, ls=ls,
                            label=f"{'Dynode' if rec.is_dynode else 'Anode'} ch{rec.channel}")
            mark_rise(ax_overlay, rec, with_label=True)
        if show_window:
            _mark_window(ax_overlay, peak)
        ax_overlay.axhline(0, color="black", linestyle="--", alpha=0.3)
        ax_overlay.set_ylabel("Amplitude [ADC]")
        ax_overlay.set_title(f"{title} overlay (peak {peak.peaks_id}, "
                             f"colors = channels)")
        ax_overlay.legend(loc="best", fontsize=8, ncol=2)
        ax_overlay.grid(True, alpha=0.2)

        for ax, ch in zip(axes[1:], channels):
            for rec in records:
                if rec.channel != ch:
                    continue
                sig = trace(rec)
                ls = "--" if rec.is_dynode else "-"
                ax.plot(_time_axis(rec, len(sig), sample_interval_ns), sig,
                        color=ch_color[ch], alpha=0.9, ls=ls,
                        label=f"{'Dynode' if rec.is_dynode else 'Anode'} ID {rec.record_id}")
                mark_rise(ax, rec, with_label=False)
            if show_window:
                for rec in records:
                    if rec.channel != ch or not rec.has_pulse:
                        continue
                    st_t = rec.time_ns + rec.pulse_start_sample * sample_interval_ns
                    ed_t = rec.time_ns + rec.pulse_end_sample * sample_interval_ns
                    ax.axvline(st_t, color="orange", linestyle="--", lw=1.0,
                               alpha=0.8, label=f"pulse st {st_t:.0f}ns")
                    ax.axvline(ed_t, color="orange", linestyle=":", lw=1.0,
                               alpha=0.8, label=f"pulse ed {ed_t:.0f}ns")
            ax.axhline(0, color="black", linestyle="--", alpha=0.3)
            ax.set_ylabel("Amplitude [ADC]")
            ax.set_title(f"ch {ch}")
            ax.legend(loc="best", fontsize=7)
            ax.grid(True, alpha=0.2)
        axes[-1].set_xlabel("Time [ns]")
        if window:
            for ax in axes:
                ax.set_xlim(*window)
        fig.tight_layout()
        path = plot_dir / f"{prefix}_{fname}_run_{run_id}.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        saved.append(path)

    # figure 1: anode (each channel its own color, window from anode records)
    overlay_and_channels(peak.anode_records, "Anode", "anode", anode_window)
    # figure 2: dynode (each channel its own color, dashed = dynode,
    # window from dynode records so the short dynode pulses stay legible)
    overlay_and_channels(peak.dynode_records, "Dynode", "dynode", dynode_window)

    # figure 3: unified-polarity comparison (anode + dynode overlay together)
    if peak.anode_records and peak.dynode_records:
        fig, ax = plt.subplots(figsize=(14, 6))
        for rec in peak.anode_records:
            sig = trace(rec)
            ax.plot(_time_axis(rec, len(sig), sample_interval_ns), sig,
                    color=ch_color[rec.channel], alpha=0.75,
                    label=f"Anode ch{rec.channel}")
        for rec in peak.dynode_records:
            sig = trace(rec)
            ax.plot(_time_axis(rec, len(sig), sample_interval_ns), sig,
                    color=ch_color[rec.channel], alpha=0.75, ls="--",
                    label=f"Dynode LP x{dynode_scale} ch{rec.channel}")
        if show_window:
            _mark_window(ax, peak)
        ax.axhline(0, color="black", linestyle="--", alpha=0.3)
        ax.set_xlabel("Time [ns]")
        ax.set_ylabel("Amplitude [ADC]")
        ax.set_title(f"Anode vs Dynode (unified polarity) peak {peak.peaks_id}, "
                     f"colors = channels")
        ax.legend(loc="best", fontsize=8, ncol=2)
        ax.grid(True, alpha=0.2)
        # compare uses the dynode window (shortest records) so the
        # pulse-aligned anode/dynode comparison stays legible
        compare_window = dynode_window or anode_window
        if compare_window:
            ax.set_xlim(*compare_window)
        fig.tight_layout()
        path = plot_dir / f"{prefix}_compare_run_{run_id}.png"
        fig.savefig(path, dpi=120)
        plt.close(fig)
        saved.append(path)

    return saved


def plot_peak_rise_check(peak, run_data, output_dir, run_id, side="anode",
                         sample_interval_ns=4.0, margin_ns=30.0) -> list[Path]:
    """All waveforms of one side (``side`` = "anode" or "dynode") of a peak,
    zoomed to the ``[pulse_start, peak]`` region per channel (the rise-edge
    region), for visual checking.

    One panel per channel; the pulse start (orange) and the pulse extremum
    (green) are marked.  The peak is the most negative sample for the anode
    and the most positive for the dynode.  Returns saved PNG paths (empty if
    the side has no records).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from muon_analysis.features import pulse_peak_index
    from muon_analysis.filtering import SignalAccessor

    records = peak.anode_records if side == "anode" else peak.dynode_records
    if not records:
        return []
    is_dynode = side == "dynode"
    color = "crimson" if is_dynode else "royalblue"
    label = "Dynode" if is_dynode else "Anode"
    polarity = "positive" if is_dynode else "negative"

    accessor = SignalAccessor.from_run_data(run_data)
    plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    path = plot_dir / f"peak{peak.peaks_id:03d}_{side}_rise_run_{run_id}.png"

    channels = sorted({r.channel for r in records})
    fig, axes = plt.subplots(len(channels), 1,
                             figsize=(14, 3 * len(channels)), sharex=False)
    if len(channels) == 1:
        axes = [axes]
    for ax, ch in zip(axes, channels):
        for rec in records:
            if rec.channel != ch:
                continue
            wf = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                            dtype=float)
            baseline = float(np.mean(wf[:10]))
            peak_idx = pulse_peak_index(wf, signal_polarity=polarity)
            st = rec.pulse_start_sample if rec.has_pulse else peak_idx - 10
            lo = max(0, st) - int(margin_ns / sample_interval_ns)
            hi = min(len(wf), peak_idx + int(margin_ns / sample_interval_ns))
            t = rec.time_ns + np.arange(len(wf)) * sample_interval_ns
            ax.plot(t[lo:hi], wf[lo:hi], color=color,
                    label=f"{label} ID {rec.record_id}")
            ax.axvline(rec.time_ns + st * sample_interval_ns, color="orange",
                       linestyle="--", lw=1.0, alpha=0.8,
                       label=f"pulse start {rec.time_ns+st*sample_interval_ns:.0f}ns")
            ax.axvline(rec.time_ns + peak_idx * sample_interval_ns, color="green",
                       linestyle=":", lw=1.2, alpha=0.9,
                       label=f"peak {rec.time_ns+peak_idx*sample_interval_ns:.0f}ns")
            ax.axhline(baseline, color="gray", linestyle="--", alpha=0.4)
        ax.set_xlabel("Time [ns]")
        ax.set_ylabel("Amplitude [ADC]")
        ax.set_title(f"ch {ch} ({label}, pulse_start .. peak)")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return [path]


def plot_peak_anode_rise_check(peak, run_data, output_dir, run_id,
                               sample_interval_ns=4.0,
                               margin_ns=30.0) -> list[Path]:
    """Backward-compatible alias of :func:`plot_peak_rise_check` (side=anode)."""
    return plot_peak_rise_check(peak, run_data, output_dir, run_id,
                                side="anode", sample_interval_ns=sample_interval_ns,
                                margin_ns=margin_ns)


def plot_peak_waveform_from(peak, run_data, output_dir, run_id, side="anode",
                            start_offset_ns=200.0, sample_interval_ns=4.0,
                            dynode_scale=110, lp_cutoff_hz=None, fs=250e6,
                            margin_ns=60.0) -> list[Path]:
    """Plot one side's waveforms of a peak, showing only the region **after**
    ``peak.start_time_ns + start_offset_ns`` (e.g. skip the leading edge).

    One panel per channel; the x-axis starts at the cut time and extends to
    the longest record end plus ``margin_ns``.  Dynode waveforms are low-pass
    filtered (``lp_cutoff_hz``) and inverted x ``dynode_scale`` when given;
    anode waveforms are raw.  Returns saved PNG paths (empty if the side has
    no records).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from muon_analysis.filtering import SignalAccessor

    records = peak.anode_records if side == "anode" else peak.dynode_records
    if not records:
        return []
    is_dynode = side == "dynode"
    color = "crimson" if is_dynode else "royalblue"
    label = "Dynode" if is_dynode else "Anode"

    accessor = SignalAccessor.from_run_data(run_data)
    plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    t_cut = peak.start_time_ns + float(start_offset_ns)
    path = plot_dir / f"peak{peak.peaks_id:03d}_{side}_from{int(start_offset_ns)}ns_run_{run_id}.png"

    channels = sorted({r.channel for r in records})
    fig, axes = plt.subplots(len(channels), 1,
                             figsize=(14, 3 * len(channels)), sharex=True)
    if len(channels) == 1:
        axes = [axes]
    xmax = max(rec.time_ns + len(accessor.signals([rec.record_id]).reshape(-1))
               * sample_interval_ns for rec in records)

    for ax, ch in zip(axes, channels):
        for rec in records:
            if rec.channel != ch:
                continue
            sig = np.asarray(accessor.signals([rec.record_id]).reshape(-1),
                             dtype=float)
            if is_dynode:
                if lp_cutoff_hz is not None:
                    sig = apply_lowpass_filter(sig, cutoff_hz=lp_cutoff_hz, fs=fs)
                sig = sig * -dynode_scale
            t = rec.time_ns + np.arange(len(sig)) * sample_interval_ns
            keep = t >= t_cut
            ax.plot(t[keep], sig[keep], color=color, alpha=0.85,
                    label=f"{label} ID {rec.record_id}")
        ax.axhline(0, color="black", linestyle="--", alpha=0.3)
        ax.set_xlabel("Time [ns]")
        ax.set_ylabel("Amplitude [ADC]")
        ax.set_title(f"ch {ch} (t >= start+{int(start_offset_ns)}ns)")
        ax.legend(loc="best", fontsize=8)
        ax.grid(True, alpha=0.2)
        ax.set_xlim(t_cut, xmax + margin_ns)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return [path]


def plot_peak_sum_waveform(peak, anode_sum, dynode_sum, output_dir, run_id,
                           sample_interval_ns=4.0, ref=50,
                           dynode_invert=False, bounds=None) -> list[Path]:
    """Plot the aligned summed waveforms (anode_sum, dynode_sum) of a peak.

    x axis is relative to the alignment reference (``ref`` samples before the
    pulse start), in ns.  ``dynode_invert`` flips the dynode sum to negative
    (for unified polarity with the negative anode).  ``bounds`` may carry
    pulse boundaries ``{side: (start, end)}`` from the sum pulse finder —
    drawn as dashed vertical lines (start ``--``, end ``:``).  Returns saved
    PNG path (empty if no sums).
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    if anode_sum is None and dynode_sum is None:
        return []
    plot_dir = Path(output_dir)
    plot_dir.mkdir(parents=True, exist_ok=True)
    suffix = "_inv" if dynode_invert else ""
    path = plot_dir / f"peak{peak.peaks_id:03d}_sum_compare{suffix}_run_{run_id}.png"

    fig, ax = plt.subplots(figsize=(14, 6))
    for arr, color, label in ((anode_sum, "royalblue", "Anode sum (aligned)"),
                              (dynode_sum, "crimson",
                               "Dynode sum (aligned, x110, flipped)")):
        if arr is None:
            continue
        if label.startswith("Dynode") and dynode_invert:
            arr = -arr
        x = (np.arange(len(arr)) - ref) * sample_interval_ns
        ax.plot(x, arr, color=color, alpha=0.85, label=label)
    if bounds:
        for side, (st, ed) in bounds.items():
            c = "royalblue" if side == "anode" else "crimson"
            ax.axvline((st - ref) * sample_interval_ns, color=c,
                       linestyle="--", lw=1.2, alpha=0.8,
                       label=f"{side} sum start {st} ({int((st-ref)*sample_interval_ns)}ns)")
            ax.axvline((ed - ref) * sample_interval_ns, color=c,
                       linestyle=":", lw=1.4, alpha=0.8,
                       label=f"{side} sum end {ed} ({int((ed-ref)*sample_interval_ns)}ns)")
    ax.axhline(0, color="black", linestyle="--", alpha=0.3)
    ax.set_xlabel("Time from pulse-start alignment [ns]")
    ax.set_ylabel("Amplitude [ADC] (sum over channels)")
    ax.set_title(f"peak {peak.peaks_id} aligned summed waveforms "
                 f"({peak.n_channels} ch)")
    ax.legend(loc="best", fontsize=8)
    ax.grid(True, alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return [path]
