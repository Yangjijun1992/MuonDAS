#!/usr/bin/env python3
"""Batch analysis driver for many run_ids, processed in groups with
parallelism and a memory/cache guard.

Reads run_ids from a CSV (docs/tpc_runs.csv) or a plain list, groups them
(small groups, e.g. 3), and processes each group with the runs in parallel.
Before each group it checks available memory and *pauses* (waits) if free
memory is too low, so a huge data load never exhausts RAM/cache.

Runs whose output already exists (``<outdir><run_id>/events_run_<run_id>.csv``)
are treated as done and skipped, so the batch is resumable.

Usage:
  python scripts/run_batch.py --csv docs/tpc_runs.csv \
      --out-root /tmp/mm_batch --group-size 3 \
      --min-free-gb 60 --data-root /mnt/data/TPC \
      [--no-save-plots]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import psutil

from muon_analysis.config import build_config
from muon_analysis.pipeline import analyze_run
from muon_analysis.gain import build_gain_db


def _available_gb() -> float:
    return psutil.virtual_memory().available / 1e9


def _wait_for_memory(min_free_gb: float, poll_sec: float = 15.0):
    """Pause until at least ``min_free_gb`` is available (memory guard)."""
    while True:
        free = _available_gb()
        if free >= min_free_gb:
            return
        print(f"[batch] memory low: {free:.1f} GB free (< {min_free_gb} GB); "
              f"pausing {poll_sec}s ...", flush=True)
        time.sleep(poll_sec)


def group_runs(run_ids, group_size: int):
    for i in range(0, len(run_ids), group_size):
        yield run_ids[i:i + group_size]


def read_run_ids(csv_path: str | None, extra: list[str]) -> list[str]:
    ids: list[str] = []
    if csv_path:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rid = (row.get("run_id") or "").strip()
                if rid:
                    ids.append(rid)
    for r in extra:
        ids.append(str(r).strip())
    # de-dup preserving order
    seen = set()
    return [x for x in ids if not (x in seen or seen.add(x))]


def already_done(out_root: str, run_id: str) -> bool:
    run_dir = Path(f"{out_root}{run_id}")
    return (run_dir / f"events_run_{run_id}.csv").exists()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv", type=str, default="docs/tpc_runs.csv")
    p.add_argument("run_ids", nargs="*", help="extra run_ids (optional)")
    p.add_argument("--out-root", type=str, default="/tmp/mm_batch")
    p.add_argument("--group-size", type=int, default=3)
    p.add_argument("--min-free-gb", type=float, default=60.0)
    p.add_argument("--min-disk-gb", type=float, default=20.0)
    p.add_argument("--data-root", type=str, default="/mnt/data/TPC")
    p.add_argument("--config", type=str, default=None)
    p.add_argument("--no-save-plots", action="store_true")
    p.add_argument("--runtype", type=str, default="",
                   help="explicit runtype scope (empty => auto-discover)")
    p.add_argument("--runtype-candidates", type=str, default="",
                   help="comma-separated runtype candidates")
    p.add_argument("--gain-backend", type=str, default="pmtdata",
                   choices=["pmtdata", "sqlite", "csv"])
    p.add_argument("--gain-path", type=str, default="")
    args = p.parse_args(argv)

    config = build_config(args.config)
    config["data_source"]["data_root"] = args.data_root
    if args.no_save_plots:
        config["output"]["save_plots"] = False
    if args.runtype:
        config["runinfo"]["runtype"] = args.runtype
    if args.runtype_candidates:
        config["runinfo"]["runtype_candidates"] = [
            t.strip() for t in args.runtype_candidates.split(",") if t.strip()
        ]
    config["gain_db"]["backend"] = args.gain_backend
    if args.gain_path:
        if args.gain_backend == "csv":
            config["gain_db"]["csv_path"] = args.gain_path
        else:
            config["gain_db"]["sqlite_path"] = args.gain_path

    run_ids = read_run_ids(args.csv, args.run_ids)
    print(f"[batch] total run_ids: {len(run_ids)}", flush=True)
    print(f"[batch] out-root: {args.out_root}  group-size: {args.group_size}",
          flush=True)

    # Ensure the output root exists (analyze_run writes <root><rid>/).
    Path(args.out_root).mkdir(parents=True, exist_ok=True)

    def _disk_free_gb() -> float:
        try:
            return psutil.disk_usage(args.out_root).free / 1e9
        except FileNotFoundError:
            return psutil.disk_usage("/").free / 1e9

    groups = list(group_runs(run_ids, args.group_size))
    print(f"[batch] groups: {len(groups)}", flush=True)

    stats = {"done": 0, "skip": 0, "failed": 0, "passed_total": 0}
    for gi, group in enumerate(groups, start=1):
        todo = [rid for rid in group if not already_done(args.out_root, rid)]
        skipped = len(group) - len(todo)
        stats["skip"] += skipped
        skipped_run_ids = [r for r in group if already_done(args.out_root, r)]
        if skipped_run_ids:
            print(f"[batch] group {gi}/{len(groups)}: skipped {len(skipped_run_ids)} "
                  f"done run(s) {skipped_run_ids}", flush=True)

        if not todo:
            print(f"[batch] group {gi}/{len(groups)}: all done, skip", flush=True)
            continue

        # memory guard before starting this 3-run group (each ~80 GB)
        needed = len(todo) * 82.0
        _wait_for_memory(max(args.min_free_gb, needed * 0.25 + 20))
        disk = _disk_free_gb()
        if disk < args.min_disk_gb:
            print(f"[batch] LOW DISK ({disk:.1f} GB < {args.min_disk_gb} GB); "
                  f"PAUSING batch.", flush=True)
            return 1

        print(f"[batch] group {gi}/{len(groups)}: processing {todo} "
              f"(parallel) ...", flush=True)

        gain_db = build_gain_db(config)  # validated up front; per-run rebuilt
        results = _run_group_parallel(todo, config, args.out_root, gain_db)

        for rid, ok, passed in results:
            if ok:
                stats["done"] += 1
                stats["passed_total"] += passed
                print(f"[batch]   {rid}: OK passed={passed}", flush=True)
            else:
                stats["failed"] += 1
                print(f"[batch]   {rid}: ERROR", flush=True)

    print("=" * 60, flush=True)
    print(f"[batch] DONE: groups={len(groups)} done={stats['done']} "
          f"skip={stats['skip']} failed={stats['failed']} "
          f"passed_total={stats['passed_total']}", flush=True)
    return 0 if stats["failed"] == 0 else 1


def _run_group_parallel(todo, config, out_root, gain_db):
    from concurrent.futures import ProcessPoolExecutor
    if len(todo) == 1:
        return [_single(todo[0], config, out_root)]
    with ProcessPoolExecutor(max_workers=len(todo)) as ex:
        futs = [ex.submit(_parallel_analyze, rid, config, out_root)
                for rid in todo]
        return [fut.result() for fut in futs]


def _single(rid, config, out_root):
    rep = analyze_run(rid, config, f"{out_root}", gain_db=None,
                      use_cache=True, save_plots=config["output"]["save_plots"])
    return (rid, rep.ok, rep.passed_events)


def _parallel_analyze(rid, config, out_root):
    return _single(rid, config, out_root)


if __name__ == "__main__":
    sys.exit(main())
