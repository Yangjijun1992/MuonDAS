"""High-level pipeline orchestration.

Mirrors the structure of the reference ``examples/pipeline.py``:
``analyze_runs`` loops over runs, resolves runinfo, reads raw data, applies
matching/filtering/feature analysis, saves outputs and handles per-run
errors without aborting the batch.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from muon_analysis.config import build_config
from muon_analysis import cache
from muon_analysis.filtering import filter_candidates
from muon_analysis.gain import build_gain_db
from muon_analysis.matching import match_events
from muon_analysis.io.runinfo import get_runinfo, RunInfoError
from muon_analysis.io.readers import read_data
from muon_analysis import output as out_mod


@dataclass
class RunReport:
    """Per-run summary of an analysis pass."""

    run_id: str
    ok: bool
    total_events: int = 0
    matched_events: int = 0
    passed_events: int = 0
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
    )


def _summarize_run_data(run_data) -> int:
    try:
        records = getattr(run_data.data, "records", None)
        if records is not None:
            return int(len(records))
    except Exception:
        pass
    return 0


def analyze_run(
    run_id: int | str,
    config: Dict[str, Any],
    output_dir: str | Path,
    gain_db=None,
    use_cache: bool = True,
    save_plots: bool = True,
    plot_ids: Optional[Sequence[int]] = None,
) -> RunReport:
    """Analyse a single run through the full pipeline."""
    report = RunReport(run_id=str(run_id), ok=False)

    try:
        runtype = config["runinfo"].get("runtype", "") or None
        candidates = config["runinfo"].get("runtype_candidates") or None
        ri = get_runinfo(
            run_id,
            config["data_source"].get("data_root", "/mnt/data/TPC"),
            runtype=runtype,
            runtype_candidates=candidates,
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
    print(f"[run_id={ri.run_id}] datatype     = {ri.datatype}")
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

    # --- gain DB ---
    if gain_db is None:
        # Query gain for the run actually being analyzed (not a fixed id).
        gain_db = build_gain_db(config, run_id=ri.run_id)
    gain_db_version = gain_db.version

    # --- filtering ---
    try:
        candidates = filter_candidates(match_df, run_data, gain_db, config)
    except Exception as e:
        report.error = f"filter: {e}"
        print(f"[run_id={ri.run_id}] ERROR: {report.error}")
        return report
    report.passed_events = len(candidates)
    print(f"[run_id={ri.run_id}] matched={report.matched_events} "
          f"passed={report.passed_events}")

    # --- persist: CSV / NPY ---
    # Per-run output directory keeps the full zero-padded run_id so runs are
    # easy to recognize (e.g. --out-dir /tmp/mm_out -> /tmp/mm_out00183).
    run_out_dir = Path(f"{output_dir}{ri.run_id}")
    run_out_dir.mkdir(parents=True, exist_ok=True)
    df = out_mod.candidates_to_dataframe(candidates, config,
                                         gain_db_version, ri.run_id)
    csv_path = out_mod.save_events_csv(df, run_out_dir, ri.run_id)
    report.outputs.append(str(csv_path))
    print(f"[run_id={ri.run_id}] CSV: {csv_path}")

    if config.get("output", {}).get("save_waveforms", True) and candidates:
        wf = _gather_waveform_clips(candidates, run_data, config)
        if len(wf):
            npz = out_mod.save_waveforms_npy(wf, run_out_dir, ri.run_id)
            report.outputs.append(str(npz))
            print(f"[run_id={ri.run_id}] waveforms: {npz}")

    # --- plots ---
    if save_plots and config.get("output", {}).get("save_plots", True):
        try:
            plots = _make_plots(run_data, candidates, df, ri.run_id,
                                run_out_dir, config, plot_ids)
            report.outputs.extend(plots)
            for p in plots:
                print(f"[run_id={ri.run_id}] plot: {p}")
        except Exception as e:
            print(f"[run_id={ri.run_id}] plotting error: {e}")

    report.ok = True
    out_mod.save_run_summary_metadata(run_out_dir, ri.run_id, report.outputs)
    return report


def _gather_waveform_clips(candidates, run_data, config) -> np.ndarray:
    accessor = _accessor(run_data)
    plot_len = int(config.get("plotting", {}).get("plot_len", 100))
    clips = []
    for c in candidates:
        a = _sig(accessor, c.anode_idx, plot_len)
        d = _sig(accessor, c.dynode_idx, plot_len)
        clips.append(np.stack([a, d]))
    if not clips:
        return np.empty((0, 2, plot_len), dtype=float)
    return np.stack(clips)


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


def _make_plots(run_data, candidates, df, run_id, output_path, config,
                plot_ids) -> List[str]:
    from muon_analysis.plotting.distributions import plot_distributions
    from muon_analysis.plotting.waveforms import plot_pmt_comparison

    accessor = _accessor(run_data)
    saved: List[str] = []

    plot_cfg = config.get("plotting", {})
    num_samples = int(plot_cfg.get("num_samples", 3))
    plot_len = int(plot_cfg.get("plot_len", 100))
    dynode_scale = float(plot_cfg.get("dynode_scale", 110))
    sample_interval_ns = float(plot_cfg.get("sample_interval_ns", 4))
    lp_cutoff = plot_cfg.get("dynode_lp_cutoff_hz")
    if lp_cutoff is not None:
        lp_cutoff = float(lp_cutoff)

    anode_idx = [c.anode_idx for c in candidates]
    dynode_idx = [c.dynode_idx for c in candidates]

    if anode_idx:
        anode_records = run_data.anode_records
        dynode_records = run_data.dynode_records

        selected_ano = anode_records[np.isin(anode_records["record_id"], anode_idx)]
        selected_dyn = dynode_records[np.isin(dynode_records["record_id"], dynode_idx)]
        p = plot_pmt_comparison(
            selected_ano, selected_dyn, accessor, output_path, run_id,
            channel_id=None, num_samples=num_samples,
            plot_length=plot_len, dynode_scale=dynode_scale,
            sample_interval_ns=sample_interval_ns,
            lp_cutoff_hz=lp_cutoff,
            fs=float(plot_cfg.get("fs", 250e6)),
            order=4,
        )
        if p:
            saved.append(str(p))

    if len(df):
        saved.extend(str(p) for p in plot_distributions(df, output_path, run_id))

    if plot_ids:
        for rid in plot_ids:
            p = _plot_by_id(run_data, rid, output_path, run_id, config)
            if p:
                saved.append(str(p))
    return saved


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


def analyze_runs(
    run_ids: Sequence[int | str],
    output_dir: str,
    data_root: str = "/mnt/data/TPC",
    config_path: Optional[str] = None,
    use_cache: bool = True,
    save_plots: bool = True,
    plot_ids: Optional[Sequence[int]] = None,
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
        } for rid in run_ids]
        try:
            with ProcessPoolExecutor() as ex:
                reports = list(ex.map(_parallel_worker, jobs))
        except Exception as e:
            print(f"Parallel execution failed ({e}); falling back to sequential.")
            reports = [analyze_run(rid, config, output_path,
                                   gain_db=None, use_cache=use_cache,
                                   save_plots=save_plots, plot_ids=plot_ids)
                       for rid in run_ids]
    else:
        for rid in run_ids:
            reports.append(analyze_run(rid, config, output_path, gain_db=None,
                                       use_cache=use_cache,
                                       save_plots=save_plots,
                                       plot_ids=plot_ids))
            print()

    ok = sum(1 for r in reports if r.ok)
    print("=" * 60)
    print("Analysis Summary")
    print("=" * 60)
    print(f"  Runs processed: {ok} / {len(run_ids)}")
    for r in reports:
        status = "OK" if r.ok else "ERROR"
        print(f"    {r.run_id}: {status} matched={r.matched_events} "
              f"passed={r.passed_events}" + (f" ({r.error})" if r.error else ""))
    print("=" * 60)
    return 0 if ok == len(run_ids) else 1
