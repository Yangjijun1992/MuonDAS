#!/usr/bin/env python
import sys, os
sys.path.insert(0, "/home/yjj/MuonDAS/src")
import numpy as np, pandas as pd
from muon_analysis.config import build_config
from muon_analysis.io.runinfo import get_runinfo
from muon_analysis.io.readers import read_data
from muon_analysis.matching import match_events
from muon_analysis.clustering import cluster_peaks
from muon_analysis.pulsefinding import compute_peak_start_end
from muon_analysis.features import compute_peak_features
from muon_analysis.gain import build_gain_db

cfg = build_config()
PARAMS=['height','width','rise_time','width_ns','width_90area','width_50area','area_ano','area_dyn','anode_area_pe','dynode_area_pe','anode_sum_area','dynode_sum_area']
OUT='/mnt/data/tmp/muon_analysis/co60_calib'
os.makedirs(OUT, exist_ok=True)
rows=[]
for rid in ['00513','00514','00515','00516']:
    try:
        ri = get_runinfo(rid, cfg['data_source']['data_root'], runtype='run7_Xe')
        rd = read_data(ri, 'waveform_analysis_records')
        matched = match_events(rd, cfg)
        peaks = list(cluster_peaks(matched, rd, cfg))
        compute_peak_start_end(peaks, rd, cfg)
        g = build_gain_db(cfg, run_id=rid)
        for pk in peaks:
            pf=compute_peak_features(pk, rd, g, cfg)
            d={k:getattr(pf,k) for k in PARAMS}
            d.update({'run_id':rid,'peaks_id':pk.peaks_id,'n_ch':pk.n_channels,
                      'anode_area_pe_recon':pf.anode_area_pe_recon,'n_anode_saturated':pf.n_anode_saturated})
            rows.append(d)
        msg=f"[{rid}] pairs={len(matched)} peaks={len(peaks)} 7ch={sum(1 for p in peaks if p.n_channels==7)}"
        print(msg, flush=True)
        with open(os.path.join(OUT,'progress.log'),'a') as f: f.write(msg+'\n')
    except Exception as e:
        msg=f"[{rid}] ERROR {e}"; print(msg, flush=True)
        with open(os.path.join(OUT,'progress.log'),'a') as f: f.write(msg+'\n')

df=pd.DataFrame(rows)
df.to_csv(os.path.join(OUT,'peak_level.csv'), index=False)
print(f"DONE total peaks={len(df)} 7ch={(df.n_ch==7).sum() if len(df) else 0}")
print(os.path.join(OUT,'peak_level.csv'))
