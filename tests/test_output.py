import numpy as np
import pandas as pd

from muon_analysis import output as out_mod
from muon_analysis.config import build_config
from muon_analysis.filtering import Candidate


def test_candidates_to_dataframe(tmp_path):
    cfg = build_config()
    cands = [
        Candidate(anode_idx=100, dynode_idx=200, channel=0, dt_ns=5.0,
                  anode_area_pe=1.0, dynode_area_pe=2.0,
                  anode_seg_area_pe=10.0, dynode_seg_area_pe=20.0,
                  event_length=7000),
        Candidate(anode_idx=101, dynode_idx=201, channel=1, dt_ns=6.0,
                  anode_area_pe=3.0, dynode_area_pe=4.0,
                  anode_seg_area_pe=30.0, dynode_seg_area_pe=40.0,
                  event_length=8000),
    ]
    df = out_mod.candidates_to_dataframe(cands, cfg, "gains-v1", "00179")
    assert len(df) == 2
    assert df["event_id"].tolist() == [0, 1]
    assert (df["parameter_version"] == cfg["parameter_version"]).all()
    assert (df["gain_db_version"] == "gains-v1").all()


def test_save_events_csv(tmp_path):
    df = pd.DataFrame({"a": [1, 2]})
    p = out_mod.save_events_csv(df, tmp_path, "00179")
    assert p.exists()
    pd.testing.assert_frame_equal(pd.read_csv(p), df)


def test_save_waveforms_npy(tmp_path):
    wf = np.ones((2, 2, 100))
    p = out_mod.save_waveforms_npy(wf, tmp_path, "00179")
    assert p.exists()
    data = np.load(p)
    assert np.array_equal(data["waveforms"], wf)
