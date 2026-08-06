#!/usr/bin/env python3
"""Generate minimal synthetic run data for offline development/testing.

Writes a runinfo.json plus ``.npy`` records & waveforms under
``<data_root>/run_R8520/<run_id>/`` so the pipeline can be exercised with the
``npy`` backend without python's ``waveform_analysis`` / ``pmtdata`` packages.

Usage:
  python scripts/sample_data.py --run-id 00179 --out /tmp/muon_demo --n 2000
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

    ano_rec, ano_wf = block(ANODE_BOARD, base + 16, 2000, "negative", 120.0)
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
    args = p.parse_args(argv)

    run_dir, raw_dir = generate(args.run_id, args.out, args.n, args.seed,
                                args.runtype)
    print("Generated run data:")
    print(f"  runinfo : {run_dir / 'runinfo.json'}")
    print(f"  raw dir : {raw_dir}")
    print(f"  records : {raw_dir / 'records_raw.npy'}")
    print(f"  waveforms: {raw_dir / 'records_waveforms.npy'}")
    print()
    print("Run the pipeline with the npy backend and a relaxed filter, e.g.:")
    print(f"  python scripts/run_analysis.py {args.run_id} "
          f"--data-root {args.out}")


if __name__ == "__main__":
    main()
