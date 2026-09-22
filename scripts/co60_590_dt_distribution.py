#!/usr/bin/env python
"""Anode/dynode matched delta-time distribution for the Co60 590+ run set (v2).

For every run of ``docs/run7_xe_calibration_run_590_plus.csv`` the raw
``dt = t_dyn - t_ano`` is collected with a wide window (no shift applied) and
again after the configured global dynode shift, per channel.  Produces the
dt distribution figures used by the pipeline documentation."""
import sys
import os
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import get_matched_indices_by_channel, shift_time_records

SHIFT = -16.0
RAW_WIN = (-200.0, 300.0)
WIN = (0.0, 40.0)
TMP = "/mnt/data/tmp/muon_analysis/co60_590"
DOCS = "/home/yjj/MuonDAS/docs/figures"
NAME = "co60_590_v2_matched_dt.png"
os.makedirs(TMP, exist_ok=True)

cfg = build_config()
runs = [f"{int(r):05d}" for r in pd.read_csv(
    "/home/yjj/MuonDAS/docs/run7_xe_calibration_run_590_plus.csv")["run_id"]]
print(f"runs = {len(runs)}", flush=True)

raw_parts, shifted_parts, ch_parts, rows = [], [], [], []
for rid in runs:
    ri = get_runinfo(rid, cfg["data_source"]["data_root"], runtype="run7_Xe")
    rd = read_data(ri, "waveform_analysis_records")
    an = rd.anode_records
    dyn_raw = np.copy(rd.dynode_records)
    dyn_shift = shift_time_records(np.copy(rd.dynode_records), SHIFT)

    m_raw = get_matched_indices_by_channel(an, dyn_raw, *RAW_WIN)
    m_sh = get_matched_indices_by_channel(an, dyn_shift, *WIN)
    raw_parts.append(m_raw["dt"].to_numpy())
    shifted_parts.append(m_sh["dt"].to_numpy())
    for ch, g in m_sh.groupby("channel"):
        ch_parts.append(pd.DataFrame({"channel": int(ch), "dt": g["dt"].to_numpy()}))
    rows.append({"run_id": rid, "n_anode": len(an), "n_dynode": len(dyn_raw),
                 "n_raw": len(m_raw), "n_shifted": len(m_sh),
                 "raw_median": float(m_raw["dt"].median()),
                 "shifted_median": float(m_sh["dt"].median())})
    print(f"[{rid}] raw={len(m_raw)} shifted={len(m_sh)} "
          f"med_raw={m_raw['dt'].median():.1f} med_sh={m_sh['dt'].median():.1f}",
          flush=True)

raw = np.concatenate(raw_parts)
sh = np.concatenate(shifted_parts)
chd = pd.concat(ch_parts, ignore_index=True)
summary = pd.DataFrame(rows)
summary.to_csv(f"{TMP}/matched_dt_summary.csv", index=False)
np.save(f"{TMP}/matched_dt_raw.npy", raw)
np.save(f"{TMP}/matched_dt_shifted.npy", sh)
chd.to_csv(f"{TMP}/matched_dt_by_channel.csv", index=False)
print(f"\nraw n={len(raw)} median={np.median(raw):.2f}")
print(f"shifted n={len(sh)} median={np.median(sh):.2f} "
      f"within[{WIN[0]:g},{WIN[1]:g}]={np.mean((sh >= WIN[0]) & (sh <= WIN[1])) * 100:.2f}%")

fig, axes = plt.subplots(1, 3, figsize=(30, 9))
axes[0].hist(raw, bins=np.arange(RAW_WIN[0], RAW_WIN[1] + 2, 2), color="navy",
             histtype="step", lw=1.6)
axes[0].axvline(np.median(raw), color="red", ls="--", lw=2.4,
                label=f"median = {np.median(raw):.2f} ns")
axes[0].axvline(0, color="k", ls=":", lw=1.6)
axes[0].set_yscale("log")
axes[0].set_xlabel("raw  t_dyn - t_ano  [ns]  (no shift)", fontsize=20, fontweight="bold")
axes[0].set_ylabel("pairs (log)", fontsize=20, fontweight="bold")
axes[0].set_title("before shift", fontsize=20)
axes[0].legend(fontsize=15)
axes[0].grid(True, alpha=0.25)

axes[1].hist(sh, bins=np.arange(WIN[0] - 20, WIN[1] + 22, 1), color="seagreen",
             histtype="step", lw=1.6)
axes[1].axvline(np.median(sh), color="red", ls="--", lw=2.4,
                label=f"median = {np.median(sh):.2f} ns")
axes[1].axvspan(WIN[0], WIN[1], color="orange", alpha=0.12,
                label=f"match window [{WIN[0]:g}, {WIN[1]:g}] ns")
axes[1].set_xlabel(f"matched  t_dyn - t_ano  [ns]  (shift {SHIFT:+.0f} ns)",
                   fontsize=20, fontweight="bold")
axes[1].set_ylabel("pairs", fontsize=20, fontweight="bold")
axes[1].set_title(f"after shift   n={len(sh):,}", fontsize=20)
axes[1].legend(fontsize=15)
axes[1].grid(True, alpha=0.25)

for ch in sorted(chd.channel.unique()):
    v = chd[chd.channel == ch].dt.to_numpy()
    axes[2].hist(v, bins=np.arange(-4, 44, 1), histtype="step", lw=1.6,
                 label=f"ch{ch} (med {np.median(v):.1f})")
axes[2].axvspan(WIN[0], WIN[1], color="orange", alpha=0.12)
axes[2].set_xlabel(f"matched  t_dyn - t_ano  [ns]  (shift {SHIFT:+.0f} ns)",
                   fontsize=20, fontweight="bold")
axes[2].set_ylabel("pairs", fontsize=20, fontweight="bold")
axes[2].set_title("per channel", fontsize=20)
axes[2].legend(fontsize=13, ncol=2)
axes[2].grid(True, alpha=0.25)

fig.suptitle(f"Co60 590+ v2 matched anode/dynode delta-time "
             f"(runs {runs[0]}-{runs[-1]}, n={len(runs)} runs, {len(sh):,} pairs)",
             fontsize=22, fontweight="bold")
fig.tight_layout(rect=(0, 0, 1, 0.95))
for out in (f"{DOCS}/{NAME}", f"{TMP}/{NAME}"):
    fig.savefig(out, dpi=150)
plt.close(fig)
print("saved", NAME)
