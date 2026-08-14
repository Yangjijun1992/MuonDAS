"""Shared synthetic-data fixtures for tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from muon_analysis.io.data import RunData
from muon_analysis.models import RunInfo


@pytest.fixture
def conftest_run_data():
    return build_synthetic_run_data()



def make_waveform(length=200, amplitude=100.0, polarity="positive", seed=0,
                  start=30, pulse=True, noise=2.0):
    rng = np.random.default_rng(seed)
    wf = rng.normal(0, noise, length).astype(float)
    if pulse:
        width = 12.0
        gauss = np.exp(-((np.arange(length) - (start + width)) ** 2) / (2 * width ** 2))
        if polarity == "negative":
            gauss = -gauss
        wf += amplitude * gauss
    return wf


def build_synthetic_run_data(n=60, seed=42):
    """Return (run_data, anode_records, dynode_records) with matched pairs.

    Anode & dynode share the same time base; anode is shifted +6 ns so that
    after the +6 ns dynode shift in ``matching``, dt ≈ 0 within [0,30] ns.
    """
    rng = np.random.default_rng(seed)
    channels = np.tile(np.array([0, 1, 2, 3]), n // 4 + 1)[:n]
    base = np.sort(rng.integers(0, 100000, size=n))

    length = 200
    dyn_wf_store = {}
    ano_wf_store = {}

    dyn_dtype = [("time", "i8"), ("channel", "i4"), ("board", "i4"),
                 ("record_id", "i8"), ("event_length", "i4")]
    dyn_rec = np.zeros(n, dtype=dyn_dtype)
    ano_rec = np.zeros(n, dtype=dyn_dtype)

    for i in range(n):
        dyn_rec["time"][i] = int(base[i])
        dyn_rec["channel"][i] = channels[i]
        dyn_rec["board"][i] = 1
        dyn_rec["record_id"][i] = 1000 + i
        dyn_rec["event_length"][i] = length

        ano_rec["time"][i] = int(base[i] + 6)
        ano_rec["channel"][i] = channels[i]
        ano_rec["board"][i] = 0
        ano_rec["record_id"][i] = 2000 + i
        ano_rec["event_length"][i] = length

        dyn_wf_store[1000 + i] = make_waveform(length, amplitude=2.0,
                                               polarity="positive", seed=i)
        ano_wf_store[2000 + i] = make_waveform(length, amplitude=120.0,
                                               polarity="negative", seed=i)

    combined_records = np.concatenate([ano_rec, dyn_rec])

    data = SimpleNamespace(records=combined_records, signals=None)
    data.signals = lambda ids: np.stack(
        [dyn_wf_store.get(int(i), ano_wf_store.get(int(i))) for i in ids]
    )

    ri = RunInfo(run_id="00179", runtype="run_R8520", run_dir=Path("/x"),
                 runinfo_path=Path("/x/runinfo.json"), raw_dir=Path("/x/RAW"),
                 datatype=["spe gain"])
    run_data = RunData(runinfo=ri, data=data, dynode_records=dyn_rec,
                       anode_records=ano_rec, data_format="test")
    return run_data, ano_rec, dyn_rec


def make_gain_db(channel_gains=(1e6, 2e6, 3e6, 4e6)):
    """A tiny in-memory gain DB for tests."""
    from muon_analysis.gain import GainDB

    class FakeGainDB(GainDB):
        def __init__(self, gains):
            self._gains = dict(gains)
            self._version = "test-gains"

        def get_gain(self, channel_id):
            if int(channel_id) not in self._gains:
                raise KeyError(channel_id)
            return self._gains[int(channel_id)]

        @property
        def version(self):
            return self._version

    gains = {ch: g for ch, g in enumerate(channel_gains)}
    return FakeGainDB(gains)
