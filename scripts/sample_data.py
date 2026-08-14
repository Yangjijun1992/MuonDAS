#!/usr/bin/env python3
"""Generate minimal synthetic run data for offline development/testing.

Writes a runinfo.json plus ``.npy`` records & waveforms under
``<data_root>/run_R8520/<run_id>/`` so the pipeline can be exercised with the
``npy`` backend without python's ``waveform_analysis`` / ``pmtdata`` packages.
An optional SQLite gain DB (``--gain-db``) and JSON PMT pattern
(``--pattern``) enable the gain / COG / track stages offline.

Usage:
  python scripts/sample_data.py --run-id 00179 --out /tmp/muon_demo \
      --gain-db /tmp/muon_demo/gains.db --pattern /tmp/muon_demo/pattern.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from muon_analysis.io.data import ANODE_BOARD, DYNODE_BOARD  # noqa: E402


def make_waveform(length, amplitude, polarity, seed):
    rng = np.random.default_rng(seed)
    wf = rng.normal(0, 2, length).astype(float)
    width = 12.0
    g = np.exp(-((np.arange(length) - 45.0) ** 2) / (2 * width ** 2))
    if polarity == "negative":
        g = -g
    return wf + amplitude * g


def make_gain_db(path, run_id="00179", channels=(0, 1, 2, 3),
                 gains=(1e6, 1e6, 1e6, 1e6)):
    """Write a small SQLite gain table (run_id, channel_id, gain)."""
    import sqlite3
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS gain "
                     "(run_id TEXT, channel_id INT, gain REAL)")
        conn.executemany("INSERT OR REPLACE INTO gain VALUES (?,?,?)",
                         [(run_id, int(ch), float(g))
                          for ch, g in zip(channels, gains)])
        conn.commit()
    finally:
        conn.close()


def make_pattern(path, channels=(0, 1, 2, 3)):
    """Write a small JSON PMT pattern: pmt_id -> [x, y]."""
    pattern = {f"pmt{i}": [float(i % 2), float(i // 2)] for i in channels}
    Path(path).write_text(json.dumps(pattern, indent=2))


def generate(run_id, out_root, n, seed=0, runtype="run_R8520"):
    rng = np.random.default_rng(seed)
    rid = str(run_id).zfill(5)
    run_dir = Path(out_root) / runtype / rid
    raw_dir = run_dir / "RAW"
    raw_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "run_info": {
            "runtype": runtype,
            "outfile_name": "sample",
            "outfile_path": str(raw_dir),
        },
        "run_option": {"run_tag": "pmt test",
                       "run_comment": ["spe gain", "dark rate"]},
        "mapping": [
            {"board_id": 0, "channels": [{"ch": i, "pmt": f"pmt{i}"}
                                          for i in range(4)]},
            {"board_id": 1, "channels": [{"ch": i, "pmt": f"pmt{i}"}
                                          for i in range(4)]},
        ],
    }
    (run_dir / "runinfo.json").write_text(json.dumps(payload))

    channels = np.tile(np.array([0, 1, 2, 3]), n // 4 + 1)[:n]
    base = np.sort(rng.integers(0, 1_000_000, size=n))
    length = 200

    def block(board, times, rec_base, polarity, amp):
        rec = np.zeros(n, dtype=[("time", "i8"), ("channel", "i4"),
                                 ("board", "i4"), ("record_id", "i8"),
                                 ("event_length", "i4")])
        wfs = np.zeros((n, length))
        for i in range(n):
            rec["time"][i] = int(times[i])
            rec["channel"][i] = channels[i]
            rec["board"][i] = board
            rec["record_id"][i] = rec_base + i
            rec["event_length"][i] = length
            wfs[i] = make_waveform(length, amp, polarity, seed + i)
        return rec, wfs

    # anode leads dynode by the configured dynode_shift_ns (6 ns) so the
    # +6 ns dynode shift in matching lands dt ~ 0 within [0, 40] ns.
    ano_rec, ano_wf = block(ANODE_BOARD, base + 6, 2000, "negative", 120.0)
    dyn_rec, dyn_wf = block(DYNODE_BOARD, base, 1000, "positive", 2.0)
    records = np.concatenate([ano_rec, dyn_rec])
    waveforms = np.concatenate([ano_wf, dyn_wf])

    np.save(raw_dir / "records_raw.npy", records)
    np.save(raw_dir / "records_waveforms.npy", waveforms)
    return run_dir, raw_dir


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run-id", default="00179")
    p.add_argument("--out", default="/tmp/muon_demo")
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--runtype", type=str, default="run_R8520",
                   help="runtype directory (e.g. run6_Xe)")
    p.add_argument("--gain-db", type=str, default="",
                   help="also write a SQLite gain DB at this path")
    p.add_argument("--pattern", type=str, default="",
                   help="also write a JSON PMT pattern at this path")
    args = p.parse_args(argv)

    run_dir, raw_dir = generate(args.run_id, args.out, args.n, args.seed,
                                args.runtype)
    print("Generated run data:")
    print(f"  runinfo : {run_dir / 'runinfo.json'}")
    print(f"  raw dir : {raw_dir}")
    print(f"  records : {raw_dir / 'records_raw.npy'}")
    print(f"  waveforms: {raw_dir / 'records_waveforms.npy'}")
    if args.gain_db:
        make_gain_db(args.gain_db, run_id=str(args.run_id).zfill(5))
        print(f"  gain db : {args.gain_db}")
    if args.pattern:
        make_pattern(args.pattern)
        print(f"  pattern : {args.pattern}")
    print()
    print("Run the pipeline with the npy backend and a relaxed filter, e.g.:")
    print(f"  python scripts/run_analysis.py {args.run_id} "
          f"--data-root {args.out}")


if __name__ == "__main__":
    main()
