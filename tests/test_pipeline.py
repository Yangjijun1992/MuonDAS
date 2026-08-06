import json
from pathlib import Path

import numpy as np

from conftest import build_synthetic_run_data, make_gain_db
from muon_analysis.config import build_config
from muon_analysis.pipeline import analyze_run, analyze_runs


def _write_runinfo(root, run_id="00179"):
    rid = run_id.zfill(5)
    rinfo = Path(root) / "run_R8520" / rid / "runinfo.json"
    rinfo.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_info": {
            "runtype": "run_R8520",
            "outfile_name": "x",
            "outfile_path": str(rinfo.parent / "RAW"),
        },
        "run_option": {"run_tag": "pmt test",
                       "run_comment": ["spe gain", "dark rate"]},
    }
    rinfo.write_text(json.dumps(payload))
    return rinfo.parent


def _write_npy_data(data_root, run_data, run_id="00179"):
    """Persist run data as .npy records + waveforms for offline analysis."""
    rid = run_id.zfill(5)
    raw_dir = Path(data_root) / "run_R8520" / rid / "RAW"
    raw_dir.mkdir(parents=True, exist_ok=True)
    combined = np.concatenate([run_data.anode_records, run_data.dynode_records])
    np.save(raw_dir / "records_raw.npy", combined)

    # build waveforms aligned to combined record order by record_id
    from muon_analysis.filtering import SignalAccessor
    accessor = SignalAccessor.from_run_data(run_data)
    waves = accessor.signals(combined["record_id"])
    np.save(raw_dir / "records_waveforms.npy", waves)
    return raw_dir


def _relaxed():
    return build_config(overrides={
        "data_source": {"data_format": "npy"},
        "filtering": {
            "min_event_length": 0,
            "min_seg_area_pe": None,
            "signal_positive_polarity": {"asym_min": 0.0},
            "signal_negative_polarity": {"asym_min": 0.0},
        },
        "features": {"integral_start": 15, "integral_end": 100},
        "output": {"save_waveforms": True},
    })


def test_analyze_run_e2e(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    root = tmp_path / "data"
    _write_runinfo(root)
    raw_dir = _write_npy_data(root, run_data)

    cfg = _relaxed()
    cfg["data_source"]["data_root"] = str(root)
    cfg["data_source"]["data_dir"] = str(raw_dir)
    cfg["data_source"]["data_id"] = "00179"

    gain_db = make_gain_db([1e6, 1e6, 1e6, 1e6])

    out_dir = tmp_path / "out"
    report = analyze_run("00179", cfg, out_dir, gain_db=gain_db,
                         use_cache=False, save_plots=False)
    assert report.ok, report.error
    assert report.passed_events > 0
    assert any("events_run_00179.csv" in p for p in report.outputs)
    assert any("waveforms_run_00179.npz" in p for p in report.outputs)

    # CSV content (per-run output dir = <out_dir><run_id>)
    import pandas as pd
    csv = Path(str(out_dir) + "00179") / "events_run_00179.csv"
    assert csv.exists()
    df = pd.read_csv(csv)
    assert "run_id" in df.columns and "parameter_version" in df.columns
    assert len(df) > 0


def test_analyze_run_cache_reuse(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    root = tmp_path / "data"
    _write_runinfo(root)
    raw_dir = _write_npy_data(root, run_data)
    cfg = _relaxed()
    cfg["data_source"]["data_root"] = str(root)
    cfg["data_source"]["data_dir"] = str(raw_dir)
    cfg["output"]["cache_dir"] = str(tmp_path / "cache")
    gain_db = make_gain_db([1e6, 1e6, 1e6, 1e6])

    out1 = tmp_path / "out1"
    r1 = analyze_run("00179", cfg, out1, gain_db=gain_db, use_cache=True,
                     save_plots=False)
    assert r1.ok
    out2 = tmp_path / "out2"
    r2 = analyze_run("00179", cfg, out2, gain_db=gain_db, use_cache=True,
                     save_plots=False)
    assert r2.ok
    assert r1.passed_events == r2.passed_events


def test_sig_pads_to_length(conftest_run_data):
    run_data, _, _ = conftest_run_data
    from muon_analysis.pipeline import _accessor, _sig
    acc = _accessor(run_data)
    # waveform length in fixtures = 200; request 100 => truncate
    rid = run_data.anode_records["record_id"][0]
    assert _sig(acc, rid, 100).shape == (100,)
    # request 500 => pad to 500
    assert _sig(acc, rid, 500).shape == (500,)
    # shorter-than-request real waveform -> pad (use a 40-sample waveform)
    import numpy as np
    from types import SimpleNamespace
    fake = SimpleNamespace(
        signals=lambda ids: np.ones((1, 40)),
    )
    assert _sig(fake, 1, 100).shape == (100,)


def test_analyze_runs_aggregate(tmp_path):
    run_data, _, _ = build_synthetic_run_data()
    root = tmp_path / "data"
    _write_runinfo(root)
    raw_dir = _write_npy_data(root, run_data)
    cfg = _relaxed()
    cfg["data_source"]["data_root"] = str(root)
    cfg["data_source"]["data_dir"] = str(raw_dir)
    out_dir = tmp_path / "out"

    rc = analyze_runs(["00179"], str(out_dir), data_root=str(root),
                      config_overrides={
                          "data_source": {"data_format": "npy", "data_dir": str(raw_dir)},
                          "filtering": {
                              "min_event_length": 0, "min_seg_area_pe": None,
                              "signal_positive_polarity": {"asym_min": 0.0},
                              "signal_negative_polarity": {"asym_min": 0.0},
                          },
                          "features": {"integral_start": 15, "integral_end": 100},
                          "gain_db": {"backend": "sqlite",
                                      "sqlite_path": str(_make_sqlite(tmp_path))},
                      },
                      save_plots=False)
    assert rc == 0


def _make_sqlite(tmp_path):
    import sqlite3
    p = tmp_path / "gains.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE gain (run_id TEXT, channel_id INT, gain REAL)")
    conn.executemany("INSERT INTO gain VALUES (?,?,?)",
                     [("00179", i, 1e6) for i in range(4)])
    conn.commit()
    conn.close()
    return p
