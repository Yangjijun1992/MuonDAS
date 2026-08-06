import numpy as np
import pytest

from muon_analysis.pe_calibration import (
    pe_calibration,
    pe_fact,
    charge_to_pe,
    compute_raw_segment_pe,
    compute_integral_pe,
)
from muon_analysis.gain import CsvGainDB, SqliteGainDB, GainDBError
from muon_analysis.config import build_config


def test_pe_fact():
    assert pe_fact() == pytest.approx((2.0 / 16384) * 4e-9 / (50 * 1.6e-19) / 1e6)


def test_charge_to_pe():
    charge = 100.0
    gain = 1e6
    assert charge_to_pe(charge, gain) == pytest.approx(charge * pe_calibration(gain))


def test_pe_calibration_zero_gain():
    with pytest.raises(ZeroDivisionError):
        pe_calibration(0.0)


def test_compute_raw_segment_pe():
    from conftest import make_gain_db
    db = make_gain_db([1e6, 2e6, 3e6, 4e6])
    signals = np.ones((2, 50))
    channels = [0, 1]
    out = compute_raw_segment_pe(signals, channels, db, "positive")
    assert out[0] == pytest.approx(50 * pe_calibration(1e6))
    assert out[1] == pytest.approx(50 * pe_calibration(2e6))


def test_compute_integral_pe():
    from conftest import make_gain_db
    db = make_gain_db([1e6])
    cfg = build_config()
    signals = np.zeros((2, 200))
    signals[:, 20:40] = 1.0
    out = compute_integral_pe(signals, [0, 0], db, "positive", cfg)
    assert out[0] == pytest.approx(20 * pe_calibration(1e6))
    assert out[1] == pytest.approx(20 * pe_calibration(1e6))


def test_csv_gain_db(tmp_path):
    p = tmp_path / "gains.csv"
    p.write_text("run_id,channel_id,gain\n00179,0,1000000\n00179,1,2000000\n")
    db = CsvGainDB(str(p), run_id="00179")
    assert db.get_gain(0) == 1e6
    assert db.get_gain(1) == 2e6


def test_sqlite_gain_db(tmp_path):
    import sqlite3
    p = tmp_path / "gains.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE gain (run_id TEXT, channel_id INT, gain REAL)")
    conn.executemany("INSERT INTO gain VALUES (?,?,?)",
                     [("00179", 0, 5e6), ("00179", 1, 6e6)])
    conn.commit()
    conn.close()
    db = SqliteGainDB(str(p), run_id="00179")
    assert db.get_gain(0) == 5e6
    assert db.get_gain(1) == 6e6


def test_sqlite_missing_channel(tmp_path):
    import sqlite3
    p = tmp_path / "gains.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE gain (run_id TEXT, channel_id INT, gain REAL)")
    conn.execute("INSERT INTO gain VALUES ('00179', 0, 5e6)")
    conn.commit()
    conn.close()
    db = SqliteGainDB(str(p), run_id="00179")
    with pytest.raises(GainDBError):
        db.get_gain(99)
