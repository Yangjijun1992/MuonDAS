"""High-level pipeline orchestration.

Per-run flow (implementation plan module 12):
``runinfo → read → match → cluster(peaks) → plot(verification) → features →
filter → COG → track → output``, with per-stage progress statistics and
optional parallel processing across runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from muon_analysis import cache
from muon_analysis import output as out_mod
from muon_analysis.clustering import cluster_peaks
from muon_analysis.config import build_config
from muon_analysis.features import compute_peak_features
from muon_analysis.filtering import filter_muon_candidates
from muon_analysis.gain import build_gain_db
from muon_analysis.io.readers import read_data
from muon_analysis.io.runinfo import get_runinfo, RunInfoError
from muon_analysis.matching import match_events
from muon_analysis.pulsefinding import compute_peak_start_end


@dataclass
class RunReport:
    """Per-run summary of an analysis pass."""

    run_id: str
    ok: bool
    total_events: int = 0
    matched_events: int = 0
    peak_count: int = 0
    passed_events: int = 0
    track_count: int = 0
    outputs: List[str] = field(default_factory=list)
    error: str = ""


def _parallel_worker(job: Dict[str, Any]) -> RunReport:
    """ProcessPoolExecutor worker: unpacks a job dict (picklable)."""
    return analyze_run(
        job["run_id"],
        job["config"],
        job["output_dir"],
        gain_db=None,
        use_cache=job.get("use_cache", True),
        save_plots=job.get("save_plots", True),
        plot_ids=job.get("plot_ids"),
        plot_peaks=job.get("plot_peaks"),
    )


def _summarize_run_data(run_data) -> int:
    try:
        records = getattr(run_data.data, "records", None)
        if records is not None:
            return int(len(records))
    except Exception:
        pass
    return 0


def _peak_to_cache(peak) -> Dict[str, Any]:
    rec = lambda r: {"record_id": r.record_id, "channel": r.channel,
                     "time_ns": r.time_ns, "is_dynode": r.is_dynode}
    return {
        "peaks_id": peak.peaks_id,
        "start_time_ns": peak.start_time_ns,
        "end_time_ns": peak.end_time_ns,
        "anode_records": [rec(r) for r in peak.anode_records],
        "dynode_records": [rec(r) for r in peak.dynode_records],
        "match_rows": list(peak.match_rows),
        "channels": list(peak.channels),
    }


def _peaks_from_cache(run_id: str, config: Dict[str, Any]):
    """Rebuild :class:`Peak` objects from a cached JSON structure."""
    from muon_analysis.models import Peak, PeakRecord

    obj = cache.read_json(run_id, config, ext="_peaks.json")
    if obj is None:
        return None
    rec = lambda d: PeakRecord(**d)
    peaks = []
    for d in obj:
        peaks.append(Peak(
            peaks_id=int(d["peaks_id"]),
            start_time_ns=float(d["start_time_ns"]),
            end_time_ns=float(d["end_time_ns"]),
            anode_records=[rec(r) for r in d.get("anode_records", [])],
            dynode_records=[rec(r) for r in d.get("dynode_records", [])],
            match_rows=list(d.get("match_rows", [])),
            channels=list(d.get("channels", [])),
        ))
    return peaks


def _load_layout(config: Dict[str, Any], runinfo):
    """Load the PMT layout (file / runinfo positions / fallback); None otherwise."""
    from muon_analysis.cog import load_pmt_layout

    return load_pmt_layout(config, runinfo)


def _accessor(run_data):
    from muon_analysis.filtering import SignalAccessor
    return SignalAccessor.from_run_data(run_data)


def _sig(accessor, record_id, length):
    """Fetch a waveform and pad/truncate it to exactly ``length`` samples."""
    arr = accessor.signals([record_id]).reshape(-1)
    if arr.shape[0] >= length:
        return arr[:length].astype(float)
    out = np.zeros(length, dtype=float)
    out[: arr.shape[0]] = arr
    return out


def _gather_waveform_clips(candidates, run_data, config) -> np.ndarray:
    """Stack per-candidate (anode, dynode) waveform clips for ``.npz`` output."""
    accessor = _accessor(run_data)
    plot_len = int(config.get("plotting", {}).get("plot_len", 100))
    clips = []
    for cand in candidates:
        anode_id = cand.features.anode_record_ids[0] \
            if cand.features.anode_record_ids else None
        dynode_id = cand.features.dynode_record_ids[0] \
            if cand.features.dynode_record_ids else None
        if anode_id is None or dynode_id is None:
            continue
        clips.append(np.stack([
            _sig(accessor, anode_id, plot_len),
            _sig(accessor, dynode_id, plot_len),
        ]))
    if not clips:
        return np.empty((0, 2, plot_len), dtype=float)
    return np.stack(clips)


def _plot_by_id(run_data, record_id, output_path, run_id, config):
    from muon_analysis.plotting.waveforms import plot_by_record_id
    cfg = config.get("plotting", {})
    return plot_by_record_id(
        run_data.anode_records, run_data.dynode_records,
        _accessor(run_data), int(record_id), output_path, run_id,
        plot_len=int(cfg.get("plot_len", 100)),
        sample_interval_ns=float(cfg.get("sample_interval_ns", 4)),
        dynode_scale=float(cfg.get("dynode_scale", 110)),
        cutoff_hz=float(cfg.get("cutoff_hz", 20e6)),
        fs=float(cfg.get("fs", 250e6)),
    )


def _make_peak_verification_plots(run_data, peaks, run_id, output_path,
                                  config, plot_peaks) -> List[str]:
    """Pre-filter verification plots: pair plots + overlays for sample peaks.

    Plots a ``plotting.num_samples`` sample of peaks (first N) plus any peak
    indices explicitly requested via ``--plot-peaks``.
    """
    from muon_analysis.plotting.waveforms import (
        plot_peak_overlay,
        plot_peak_pairs,
    )

    plot_cfg = config.get("plotting", {})
    num_samples = int(plot_cfg.get("num_samples", 3))
    sample_ids = {p.peaks_id for p in peaks[:num_samples]}
    for idx in (plot_peaks or []):
        sample_ids.add(int(idx))

    saved: List[str] = []
    for peak in peaks:
        if peak.peaks_id not in sample_ids:
            continue
        try:
            pairs = plot_peak_pairs(
                peak, run_data, output_path, run_id,
                sample_interval_ns=float(plot_cfg.get("sample_interval_ns", 4)),
                dynode_scale=float(plot_cfg.get("dynode_scale", 110)),
                lp_cutoff_hz=plot_cfg.get("dynode_lp_cutoff_hz"),
                fs=float(plot_cfg.get("fs", 250e6)),
                plot_len=int(plot_cfg.get("plot_len", 100)),
            )
            overlay = plot_peak_overlay(
                peak, run_data, output_path, run_id,
                sample_interval_ns=float(plot_cfg.get("sample_interval_ns", 4)),
                dynode_scale=float(plot_cfg.get("dynode_scale", 110)),
                lp_cutoff_hz=plot_cfg.get("dynode_lp_cutoff_hz"),
                fs=float(plot_cfg.get("fs", 250e6)),
                plot_len=int(plot_cfg.get("plot_len", 100)),
            )
            saved.extend(str(p) for p in pairs + overlay)
        except Exception as e:
            print(f"[run_id={run_id}] peak {peak.peaks_id} plot error: {e}")
    return saved


def _compute_cog_coords(candidates, layout, config) -> Dict[int, tuple]:
    """COG positions per candidate (fast, no plotting)."""
    from muon_analysis.cog import cog_reconstruct_peak

    positions = layout.pmt_positions_by_id
    coords: Dict[int, tuple] = {}
    for cand in candidates:
        cog = cog_reconstruct_peak(cand.features, None, positions, config)
        if cog is not None:
            coords[cand.peaks_id] = cog
    return coords


def _reconstruct_tracks(candidates, peaks, run_data, runinfo, layout,
                        config, run_out_dir, run_id, save_plots,
                        plot_peaks) -> tuple:
    """3D track reconstruction per candidate; plots only for a sample."""
    from muon_analysis.track import plot_track, reconstruct_track, slice_peak_waveforms

    positions = layout.pmt_positions_by_id
    num_samples = int(config.get("plotting", {}).get("num_samples", 3))
    wanted = {c.peaks_id for c in candidates[:num_samples]}
    for idx in (plot_peaks or []):
        wanted.add(int(idx))

    track_plots: List[str] = []
    tracks = 0
    peak_by_id = {p.peaks_id: p for p in peaks}
    for cand in candidates:
        peak = peak_by_id.get(cand.peaks_id)
        if peak is None:
            continue
        slices = slice_peak_waveforms(peak, run_data, config)
        track = reconstruct_track(slices, runinfo, positions, config)
        if track.n_slices == 0:
            continue
        tracks += 1
        if save_plots and cand.peaks_id in wanted:
            p = plot_track(track, run_out_dir, f"{run_id}_peak{cand.peaks_id}")
            track_plots.append(str(p))
            print(f"[run_id={run_id}] track: {p}")
    return tracks, track_plots


def _make_pmt_area_maps(candidates, layout, run_out_dir, run_id, config,
                        plot_peaks) -> List[str]:
    """PMT area-map plots (layout + charge colouring + COG) for a sample."""
    from muon_analysis.plotting.pattern import plot_pmt_area_map

    num_samples = int(config.get("plotting", {}).get("num_samples", 3))
    wanted = {c.peaks_id for c in candidates[:num_samples]}
    for idx in (plot_peaks or []):
        wanted.add(int(idx))

    saved: List[str] = []
    for cand in candidates:
        if cand.peaks_id not in wanted or not cand.features.charge_per_pmt:
            continue
        p = plot_pmt_area_map(layout, cand.features.charge_per_pmt,
                              run_out_dir, run_id, index=cand.peaks_id)
        saved.append(str(p))
    return saved


def analyze_run(
    run_id: int | str,
    config: Dict[str, Any],
    output_dir: str | Path,
    gain_db=None,
    use_cache: bool = True,
    save_plots: bool = True,
    plot_ids: Optional[Sequence[int]] = None,
    plot_peaks: Optional[Sequence[int]] = None,
) -> RunReport:
    """Analyse a single run through the full peak-based pipeline."""
    report = RunReport(run_id=str(run_id), ok=False)

    try:
        runtype = config["runinfo"].get("runtype", "") or None
        candidates_rt = config["runinfo"].get("runtype_candidates") or None
        ri = get_runinfo(
            run_id,
            config["data_source"].get("data_root", "/mnt/data/TPC"),
            runtype=runtype,
            runtype_candidates=candidates_rt,
        )
    except (RunInfoError, Exception) as e:
        report.error = f"runinfo: {e}"
        print(f"[run_id={run_id}] ERROR: {report.error}")
        return report

    try:
        fmt = config["data_source"].get("data_format",
                                        "waveform_analysis_records")
        run_data = read_data(ri, fmt,
                             data_dir=config["data_source"].get("data_dir"))
    except Exception as e:
        report.error = f"read: {e}"
        print(f"[run_id={run_id}] ERROR: {report.error}")
        return report

    report.total_events = _summarize_run_data(run_data)
    print(f"[run_id={ri.run_id}] runtype      = {ri.runtype}")
    print(f"[run_id={ri.run_id}] raw_dir      = {ri.raw_dir}")
    print(f"[run_id={ri.run_id}] total events = {report.total_events}")

    # --- matching (cacheable) ---
    npy = None
    if use_cache:
        npy = cache.read_npy(ri.run_id, config, ext="_match.npy")
    if npy is not None:
        print(f"[run_id={ri.run_id}] cached match hit")
        match_df = pd.DataFrame(
            npy, columns=["dynode_idx", "anode_idx", "dt", "channel"])
        match_df["dynode_idx"] = match_df["dynode_idx"].astype(int)
        match_df["anode_idx"] = match_df["anode_idx"].astype(int)
        match_df["channel"] = match_df["channel"].astype(int)
    else:
        match_df = match_events(run_data, config)
        if use_cache:
            cache.write_npy(ri.run_id, config,
                            match_df.to_numpy(dtype=float), ext="_match.npy")
    report.matched_events = len(match_df)

    # --- clustering into peaks (cacheable) ---
    peaks = None
    cached = False
    if use_cache:
        peaks = _peaks_from_cache(ri.run_id, config)
        cached = peaks is not None
    if peaks is None:
        peaks = cluster_peaks(match_df, run_data, config)
    # peak start/end from per-channel pulse boundaries (negative pulses;
    # dynode waveforms are inverted internally).
    compute_peak_start_end(peaks, run_data, config)
    if use_cache and not cached:
        cache.write_json(ri.run_id, config,
                         [_peak_to_cache(p) for p in peaks],
                         ext="_peaks.json")
    report.peak_count = len(peaks)
    print(f"[run_id={ri.run_id}] matched={report.matched_events} "
          f"peaks={report.peak_count}")

    # --- gain DB ---
    if gain_db is None:
        gain_db = build_gain_db(config, run_id=ri.run_id)
    gain_db_version = gain_db.version

    # --- per-peak features ---
    try:
        peak_features = [
            compute_peak_features(p, run_data, gain_db, config)
            for p in tqdm(peaks, desc=f"[{ri.run_id}] features",
                          disable=not config.get("progress", True))
        ]
    except Exception as e:
        report.error = f"features: {e}"
        print(f"[run_id={ri.run_id}] ERROR: {report.error}")
        return report

    # --- muon candidate filtering (peak level) ---
    try:
        candidates = filter_muon_candidates(peaks, peak_features, config)
    except Exception as e:
        report.error = f"filter: {e}"
        print(f"[run_id={ri.run_id}] ERROR: {report.error}")
        return report
    report.passed_events = len(candidates)
    print(f"[run_id={ri.run_id}] muon candidates = {report.passed_events}")

    # Per-run output directory (zero-padded run_id, e.g. output00183).
    run_out_dir = Path(f"{output_dir}{ri.run_id}")
    run_out_dir.mkdir(parents=True, exist_ok=True)

    # --- COG positions (fast) ---
    layout = _load_layout(config, ri)
    cog_coords: Dict[int, tuple] = {}
    if layout is not None:
        cog_coords = _compute_cog_coords(candidates, layout, config)

    # --- persist: CSV (with peaks_id / record_id / cog_x / cog_y) + NPY ---
    df = out_mod.peaks_to_dataframe(candidates, config, gain_db_version,
                                    ri.run_id, cog_coords=cog_coords)
    csv_path = out_mod.save_events_csv(df, run_out_dir, ri.run_id)
    report.outputs.append(str(csv_path))
    print(f"[run_id={ri.run_id}] CSV: {csv_path}")

    if config.get("output", {}).get("save_waveforms", True) and candidates:
        wf = _gather_waveform_clips(candidates, run_data, config)
        if len(wf):
            npz = out_mod.save_waveforms_npy(wf, run_out_dir, ri.run_id)
            report.outputs.append(str(npz))
            print(f"[run_id={ri.run_id}] waveforms: {npz}")

    # --- track reconstruction + PMT area maps (sample plots) ---
    if layout is not None:
        track_plots_on = save_plots and config.get("track", {}).get(
            "save_plots", True)
        report.track_count, track_plots = _reconstruct_tracks(
            candidates, peaks, run_data, ri, layout, config,
            run_out_dir, ri.run_id, track_plots_on, plot_peaks)
        report.outputs.extend(track_plots)
        print(f"[run_id={ri.run_id}] tracks = {report.track_count}")
        if save_plots and config.get("output", {}).get("save_plots", True):
            area_maps = _make_pmt_area_maps(candidates, layout, run_out_dir,
                                            ri.run_id, config, plot_peaks)
            report.outputs.extend(area_maps)
            for p in area_maps:
                print(f"[run_id={ri.run_id}] plot: {p}")

    # --- plots: peak verification (pre-filter sample) + distributions ---
    if save_plots and config.get("output", {}).get("save_plots", True):
        try:
            verification = _make_peak_verification_plots(
                run_data, peaks, ri.run_id, run_out_dir, config, plot_peaks)
            report.outputs.extend(verification)
            for p in verification:
                print(f"[run_id={ri.run_id}] plot: {p}")
        except Exception as e:
            print(f"[run_id={ri.run_id}] peak-plot error: {e}")

        if len(df):
            from muon_analysis.plotting.distributions import plot_distributions
            dists = plot_distributions(df, run_out_dir, ri.run_id)
            report.outputs.extend(str(p) for p in dists)

    if plot_ids:
        for rid in plot_ids:
            p = _plot_by_id(run_data, rid, run_out_dir, ri.run_id, config)
            if p:
                report.outputs.append(str(p))

    report.ok = True
    out_mod.save_run_summary_metadata(run_out_dir, ri.run_id, report.outputs)
    return report


def analyze_runs(
    run_ids: Sequence[int | str],
    output_dir: str,
    data_root: str = "/mnt/data/TPC",
    config_path: Optional[str] = None,
    use_cache: bool = True,
    save_plots: bool = True,
    plot_ids: Optional[Sequence[int]] = None,
    plot_peaks: Optional[Sequence[int]] = None,
    parallel: bool = False,
    config_overrides: Optional[Dict[str, Any]] = None,
) -> int:
    """Analyse multiple runs and write results to ``output_dir``."""
    config = build_config(config_path, config_overrides)
    if data_root:
        config["data_source"]["data_root"] = data_root

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("Muon dynode/anode analysis started")
    print(f"Run IDs: {list(run_ids)}")
    print(f"Output directory: {output_path.resolve()}")
    print(f"Data root: {config['data_source']['data_root']}")
    print(f"Gain backend: {config['gain_db']['backend']}")
    print()

    reports: List[RunReport] = []

    if parallel and len(run_ids) > 1:
        from concurrent.futures import ProcessPoolExecutor
        jobs = [{
            "run_id": rid,
            "config": config,
            "output_dir": str(output_path),
            "use_cache": use_cache,
            "save_plots": save_plots,
            "plot_ids": list(plot_ids) if plot_ids else None,
            "plot_peaks": list(plot_peaks) if plot_peaks else None,
        } for rid in run_ids]
        try:
            with ProcessPoolExecutor() as ex:
                reports = list(tqdm(ex.map(_parallel_worker, jobs),
                                    total=len(jobs), desc="runs"))
        except Exception as e:
            print(f"Parallel execution failed ({e}); falling back to sequential.")
            for rid in tqdm(run_ids, desc="runs"):
                reports.append(analyze_run(rid, config, output_path,
                                           gain_db=None, use_cache=use_cache,
                                           save_plots=save_plots,
                                           plot_ids=plot_ids,
                                           plot_peaks=plot_peaks))
    else:
        for rid in tqdm(run_ids, desc="runs"):
            reports.append(analyze_run(rid, config, output_path, gain_db=None,
                                       use_cache=use_cache,
                                       save_plots=save_plots,
                                       plot_ids=plot_ids,
                                       plot_peaks=plot_peaks))
            print()

    ok = sum(1 for r in reports if r.ok)
    print("=" * 60)
    print("Analysis Summary")
    print("=" * 60)
    print(f"  Runs processed: {ok} / {len(run_ids)}")
    for r in reports:
        status = "OK" if r.ok else "ERROR"
        print(f"    {r.run_id}: {status} matched={r.matched_events} "
              f"peaks={r.peak_count} passed={r.passed_events} "
              f"tracks={r.track_count}" + (f" ({r.error})" if r.error else ""))
    print("=" * 60)
    return 0 if ok == len(run_ids) else 1
