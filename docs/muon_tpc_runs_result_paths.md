# Muon TPC Runs 分析结果存储路径清单

> 本文件记录现有分析结果的存储路径、目录结构与关联缓存位置，便于定位与归档。
> 配套：分析结果报告见 [muon_tpc_runs_analysis_report.md](muon_tpc_runs_analysis_report.md)。

## 1. 分析结果目录（成功分析的 47 个 run）

每个 run 一个独立目录，位于 `/tmp/mm_out<run_id>/`：

```
/tmp/mm_out00183/   /tmp/mm_out00184/   /tmp/mm_out00185/
/tmp/mm_out00189/   /tmp/mm_out00190/   /tmp/mm_out00191/
/tmp/mm_out00192/   /tmp/mm_out00193/   /tmp/mm_out00194/
/tmp/mm_out00195/   /tmp/mm_out00196/   /tmp/mm_out00197/
/tmp/mm_out00205/   /tmp/mm_out00206/   /tmp/mm_out00207/
/tmp/mm_out00208/   /tmp/mm_out00209/   /tmp/mm_out00210/
/tmp/mm_out00214/   /tmp/mm_out00215/   /tmp/mm_out00216/
/tmp/mm_out00217/   /tmp/mm_out00219/   /tmp/mm_out00220/
/tmp/mm_out00221/   /tmp/mm_out00222/   /tmp/mm_out00223/
/tmp/mm_out00224/   /tmp/mm_out00225/   /tmp/mm_out00226/
/tmp/mm_out00227/   /tmp/mm_out00228/   /tmp/mm_out00229/
/tmp/mm_out00230/   /tmp/mm_out00231/   /tmp/mm_out00232/
/tmp/mm_out00233/   /tmp/mm_out00234/   /tmp/mm_out00235/
/tmp/mm_out00236/   /tmp/mm_out00237/   /tmp/mm_out00238/
/tmp/mm_out00239/   /tmp/mm_out00240/   /tmp/mm_out00241/
/tmp/mm_out00242/   /tmp/mm_out00243/
```

## 2. 单 run 目录内文件结构

以 `/tmp/mm_out00183/` 为例：

| 文件 | 说明 |
|---|---|
| `events_run_00183.csv` | 候选事例级 CSV（面积/PE、event_length、channel、溯源列等） |
| `waveforms_run_00183.npz` | 候选波形片段，shape `(11, 2, 100)`（阳极/打拿极×100 点） |
| `compare_run_00183.png` | 阳极-打拿极波形叠加对比图 |
| `hist_anode_area_pe_00183.png` | 阳极面积 PE 分布直方图 |
| `hist_dynode_area_pe_00183.png` | 打拿极面积 PE 分布直方图 |
| `hist_anode_seg_area_pe_00183.png` | 阳极段面积 PE 分布直方图 |
| `hist_dt_ns_00183.png` | anode-dynode 时间差分布直方图 |
| `correlation_run_00183.png` | anode vs dynode area 相关散点图 |
| `segarea_len_run_00183.png` | 段面积 vs 波形长度 2D 直方图 |
| `run_00183_metadata.json` | 运行元数据 |

> 0-候选 run（如 00193/00197/00205 等）只有 `events_run_<id>.csv`（空）与 `run_<id>_metadata.json`，无波形/图。

## 3. 缓存目录

| 路径 | 说明 |
|---|---|
| `/tmp/muon_analysis/` | 匹配结果缓存目录（52 个 `*_match.npy`，共约 114MB） |
| `/tmp/muon_analysis/<run_id>__<参数哈希>_match.npy` | 时间匹配结果缓存（同一参数下可复用以跳过 `merge_asof`） |
| `/tmp/v1725_parts_*/` | `waveform_analysis` 分析工具 staging 临时分块目录（32 个，可安全清理） |

## 4. 暂缓 run（无结果目录）

以下 3 个 run 因读取失败已**暂缓分析**，无输出目录：
`00211`、`00212`、`00213`

## 5. 输入与文档

| 文件 | 说明 |
|---|---|
| `docs/tpc_runs.csv` | 输入 run 清单（50 个 run_id） |
| `docs/muon_tpc_runs_analysis_report.md` | 批量分析结果报告（47 成功 + 3 暂缓标记、缓存、复现命令） |
| `docs/muon_analysis_delivery.md` | 工具交付内容与模块说明 |
