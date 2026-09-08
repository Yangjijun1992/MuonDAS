#!/usr/bin/env python
import sys, os
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from scipy import stats
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.filtering import SignalAccessor
from muon_analysis.pe_calibration import pe_calibration
from muon_analysis.gain import build_gain_db

cfg = build_config()
BL = 10
OUT = "/mnt/data/tmp/muon_analysis/co60_calib"
os.makedirs(OUT, exist_ok=True)
rows = []
dt_all = []
for rid in ['00513','00514','00515','00516']:
    ri = get_runinfo(rid, cfg['data_source']['data_root'], runtype='run7_Xe')
    rd = read_data(ri, 'waveform_analysis_records')
    m = match_events(rd, cfg)
    dt_all.append(m['dt'].to_numpy())
    acc = SignalAccessor.from_run_data(rd)
    g = build_gain_db(cfg, run_id=rid)
    a_recs = rd.anode_records; d_recs = rd.dynode_records
    for _, row in m.iterrows():
        ar = a_recs[int(row.anode_idx)]; dr = d_recs[int(row.dynode_idx)]
        aw = np.asarray(acc.signals([ar['record_id']]).reshape(-1), dtype=float)
        dw = np.asarray(acc.signals([dr['record_id']]).reshape(-1), dtype=float)
        if len(aw)==0 or len(dw)==0: continue
        abl=float(np.mean(aw[:BL])); dbl=float(np.mean(dw[:BL]))
        aa=float(np.sum(np.abs(aw-abl))); da=float(np.sum(dw-dbl))
        gch = g.get_gain(int(ar['channel']))
        if not gch or da<=0: continue
        cal = pe_calibration(gch)
        rows.append({'run_id':rid,'channel':int(ar['channel']),'anode_pe':aa*cal,'dynode_pe':da*cal,'ratio':aa/da})
    print(f'[{rid}] pairs={len(m)}', flush=True)
    open(os.path.join(OUT,'progress.log'),'a').write(f'[{rid}] pairs={len(m)}\n')

ep = pd.DataFrame(rows)
ep.to_csv(os.path.join(OUT,'all_pairs_perpmt_pe.csv'), index=False)
dt_all = np.concatenate(dt_all) if dt_all else np.array([])
np.save(os.path.join(OUT,'all_matched_dt.npy'), dt_all)

# --- 图1: per-PMT 积分 2D + ratio 分布 ---
ep = ep[ep.ratio<=1000]
d=ep.dynode_pe.to_numpy(); a=ep.anode_pe.to_numpy()
fig,axes=plt.subplots(1,2,figsize=(16,7))
hb=axes[0].hist2d(d,a,bins=(120,120),cmap='viridis',cmin=1,norm=LogNorm())
axes[0].set_xlabel(r'dynode_area [PE]',fontsize=15); axes[0].set_ylabel(r'anode_area [PE]',fontsize=15)
fig.colorbar(hb[3],ax=axes[0],label='counts (log)')
axes[1].hist(ep.ratio,bins=np.arange(0,800,4),histtype='step',color='darkred',lw=1.5)
axes[1].axvline(ep.ratio.median(),color='b',ls='--',lw=2,label=f'median={ep.ratio.median():.1f}')
axes[1].set_yscale('log'); axes[1].set_xlabel('ratio = anode_pe / dynode_pe',fontsize=15); axes[1].set_ylabel('counts (log)',fontsize=15)
axes[1].legend(fontsize=12); axes[1].grid(alpha=0.3,ls=':'); axes[1].set_xlim(0,800)
fig.tight_layout()
p1=os.path.join(OUT,'co60_perpmt_2dhist_ratio.png'); fig.savefig(p1,dpi=140); plt.close(fig)

# --- 图2: dt 分布 ---
fig,ax=plt.subplots(figsize=(12,7))
ax.hist(dt_all,bins=np.arange(-5,205,2),histtype='step',color='navy',lw=1.5)
ax.axvline(np.median(dt_all),color='r',ls='--',lw=2,label=f'median={np.median(dt_all):.1f}')
ax.set_xlabel('matched dt (dynode-anode, after shift) [ns]',fontsize=15); ax.set_ylabel('counts',fontsize=15)
ax.legend(fontsize=13); ax.grid(alpha=0.3,ls=':')
fig.tight_layout()
p2=os.path.join(OUT,'co60_matched_dt_histogram.png'); fig.savefig(p2,dpi=140); plt.close(fig)

print(f"\nDONE points={len(ep)} ratio_median={ep.ratio.median():.1f}")
print(f"dt n={len(dt_all)} median={np.median(dt_all):.1f} p16={np.percentile(dt_all,16):.1f} p84={np.percentile(dt_all,84):.1f}")
print(p1); print(p2)
