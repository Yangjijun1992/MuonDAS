# Muon 事件分析：Pipeline 与架构总览

> 本文档描述从头到尾的数据处理与分析流程（Pipeline）、模块架构、关键算法约定，
> 以及定位算法问题的排查路径。供总体浏览与故障排查使用。
>
> 配套：[需求](muon_dynode_analysis_requirements.md) / [实施计划](muon_dynode_analysis_implementation_plan.md) /
> [交付内容](muon_analysis_delivery.md) / [批量结果](muon_tpc_runs_analysis_report.md)

---

## 1. 整体架构图

```
                  ┌───────────────────────────────────────────────────────────────┐
  输入run_id清单   │                        scripts / CLI                            │
  (多run/通配/CSV) │   run_analysis.py   ·   run_batch.py   ·   sample_data.py       │
                  └───────────────┬───────────────────────────────────────────────┘
                                  │ analyze_runs(单/多run, 并行) / analyze_run(单run)
                                  ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                              src/muon_analysis/                             │
   │                                                                             │
   │  ① config.py         配置加载/校验/覆盖(CLI>用户>默认) + 参数哈希            │
   │  ② io/runinfo.py     runinfo.json 发现/解析 → RunInfo(含 raw_dir/runtype)    │
   │  ③ io/readers*       读取records: waveform_analysis | npy | hdf5            │
   │     io/data.py        RunData(按board分离 dynode=1/anode=0)                  │
   │  ④ matching.py       时间匹配(移位 + merge_asof) ← 可缓存                   │
   │  ⑤ filtering.py      候选筛选(asym/长度/段面积/高度)                         │
   │  ⑥ features.py       特征量 + 积分窗口策略(固定/预留寻峰)                   │
   │     gain.py           PMT SPE gain(pmtdata/sqlite/csv)                      │
   │     pe_calibration.py 电荷→PE(pe_fact/gain)                                  │
   │  ⑦ plotting/*        波形图 + 统计分布图                                     │
   │  ⑧ output.py         CSV / .npz / PNG / metadata                             │
   │  ⑨ cache.py          /tmp/muon_analysis 匹配缓存(run_id+参数哈希)           │
   └───────────────┬─────────────────────────────────────────────────────────────┘
                   │
                   ▼
       输出: <out-dir><run_id>/{events_run_<id>.csv, waveforms.npz, *.png, metadata.json}
```

数据流（单 run）：`runinfo → read → match → filter → features/PE → plot → output`

---

## 2. 各阶段处理细节与算法约定

### 2.1 配置与参数（config.py）
- 优先级：**CLI > 用户配置文件 > 内置默认**（`config/analysis.yaml`），`_deep_merge` 递归合并。
- `param_hash(cfg)`：对处理参数做 SHA-1（排除输出/缓存等易变字段），用于缓存键与结果溯源。
- 关键参数分组见 [配置要点](#6-配置要点)。

### 2.2 run 发现与信息（io/runinfo.py）
- `normalize_run_id`：补零到 5 位。
- `discover_runinfo_path`：`<data_root>/<runtype>/<rid>/runinfo.json`。
- **runtype 作用域/自动探测**：`runtype` 显式限定搜索路径；为空时 `discover_runtype` 扫描 data_root 下候选 runtype 目录（`run_R8520` / `run5_Ar` / `run6_Xe` 等）。`runinfo.runtype`（文件内）为权威值。
- 宽松校验：run_tag/datatype 不匹配时告警并置空 datatype，不阻断（适配 TPC/muon run）。
- `RunInfo` 携带 `raw_dir`（真实数据路径）、`mapping`（board/ch→pmt_id）、`datatype` 等。

### 2.3 数据读取（io/readers*.py、io/data.py）
- 后端（`data_source.data_format`）：
  - `waveform_analysis_records`：`records_view(ctx, run_id)` 返回结构化 records（字段 `time, channel, board, record_id, event_length`）。
  - `npy` / `hdf5`：离线/中间持久化 records（可选波形 `*_waveforms.npy`）。
- `split_by_board`：`board==1 → dynode_records`，`board==0 → anode_records`，装入 `RunData`（含 `signals(ids)` 访问器）。
- 容错：单个 run 读取失败 → 打印 ERROR 并跳过，不中断批次。

### 2.4 时间匹配（matching.py）—— 关键算法
- **移位**：dynode 全局 `+dynode_shift_ns`（默认 **+16 ns**，`shift_time_records`）。
- 逐通道延迟校准：按 `channel_delay_ns` 再对 dynode 附加偏移（可空）。
- **匹配**：pandas `merge_asof`，`by='channel'`、`direction='backward'`（每个 dynode 找 ≤ 它的最近 anode）。
- **窗口**：保留 `dt = t_dyn_shifted − t_ano ∈ [min_diff, max_diff] = [0, 30] ns`。
- 输出匹配表 `[dynode_idx, anode_idx, dt, channel]`；可缓存至 `/tmp/muon_analysis/<run_id>__<hash>_match.npy`。
- **时间关系结论（实测 146 候选）**：原始 `dynode_time − anode_time ∈ [-16, 0] ns`（dynode 提前 0–16ns）；对 dynode `+16` 后落入 [0,30]。

### 2.5 候选筛选（filtering.py）
- `asymmetry_calculation`：正/负极波形不对称度 `asym=(peak−baseline)/range`（dy）或 `(baseline−valley)/range`(anode)，噪声剔除。
- 长度/段面积：`event_length >= min_event_length`，`seg_area_pe >= min_seg_area_pe`（大脉冲挑选）。
- 高度阈值（可选，anode/dynode 分别设置）。
- 面积（`area_pe` 窗口内、`seg_area_pe` 整段）由 pe_calibration 计算并写入 records。
- 输出 `Candidate`（含 anode/dynode record_id、channel、dt、面积、event_length、原始 anode/dynode time 于 metadata）。

### 2.6 特征量 / PE 标定（features.py、gain.py、pe_calibration.py）
- **积分窗口策略**：`IntegrationWindowResolver` 抽象，默认 `FixedWindowResolver(start,end)`；预留 `PeakFinderWindowResolver`（待寻峰算法定位波形起点）。
- 特征量：peak height、charge、rise_time、width（FWHM）、baseline。
- **gain**：`build_gain_db(config, run_id)` 按当前 run 查询；pmtdata 读 `spe_gain` 列，该 run 无条目时回退每通道最新值。
- **PE**：`pe_fact=(2/16384)*4e-9/(50*1.6e-19)/1e6`，`pe_calib=pe_fact/gain`，`area_pe=∫window × pe_calib`。

### 2.7 可视化（plotting/waveforms.py、distributions.py）
- `plot_pmt_comparison`：叠加阳极/打拿极（dynode 反相放大 `×dynode_scale`；可选 `dynode_lp_cutoff_hz` 低通滤波）。
- `plot_by_record_id`：按 record_id 时间对齐绘制单对（dynode 低通 20MHz）。
- `plot_distributions` / `plot_correlation` / 2D 直方：PE 谱、dt 谱、anode-dynode 相关、seg_area vs length。

### 2.8 输出（output.py）
- 每 run 目录 `<out-dir><run_id>/`（run_id 补零，便于识别）。
- 文件：`events_run_<id>.csv`（含溯源列 parameter_version / gain_db_version）、`waveforms_*.npz`、各 PNG、`run_<id>_metadata.json`。

### 2.9 缓存（cache.py）
- 目录 `/tmp/muon_analysis/`，键 `run_id + 参数哈希`。
- `--show-cache` 列出、`--clear-cache` 清空；空间不足警告不自动清除。
- 注意：`waveform_analysis` 读取时在 `/tmp/v1725_parts_*` 分块暂存；多 run 并行可能冲突（见 §5 排查）。

---

## 3. 模块职责与代码位置对照

| 阶段 | 模块 | 关键函数 |
|---|---|---|
| 配置 | `config.py` | `build_config` / `param_hash` |
| run信息 | `io/runinfo.py` | `get_runinfo` / `discover_runtype` |
| 读数据 | `io/readers.py` `io/readers_alt.py` `io/data.py` | `read_data` / `split_by_board` |
| 时间匹配 | `matching.py` | `match_events` / `get_matched_indices_by_channel` |
| 筛选 | `filtering.py` | `filter_candidates` / `asymmetry_calculation` |
| 特征/PE | `features.py` `gain.py` `pe_calibration.py` | `compute_features` / `build_gain_db` / `compute_integral_pe` |
| 绘图 | `plotting/waveforms.py` `plotting/distributions.py` | `plot_pmt_comparison` / `plot_distributions` |
| 输出 | `output.py` | `save_events_csv` / `save_waveforms_npy` |
| 缓存 | `cache.py` | `read_npy` / `write_npy` / `show_cache` |
| 编排 | `pipeline.py` | `analyze_run` / `analyze_runs` / `_make_plots` |

---

## 4. 编排与并行（pipeline.py、scripts/run_batch.py）

- `analyze_run(run_id, config, out_dir)`：单 run 全流程，逐阶段 try/except。
- `analyze_runs(run_ids, out_dir, ...)`：多 run 编排，`parallel=True` 时按 run 粒度 `ProcessPoolExecutor`。
- `scripts/run_batch.py`：批量驱动，**每 N 个 run 一组**（默认 3）、组内并行、内存/磁盘保护、断点续跑（已有输出跳过）。

---

## 5. 排查算法问题的路径

按"现象 → 定位阶段 → 检查项"排查：

| 现象 | 优先检查阶段 | 排查要点 |
|---|---|---|
| 读取失败 / `/tmp/v1725_parts_*` 缺失 | §2.3 读 | 并行度过高导致暂存冲突；改为串行/降并行度重试；确认 `waveform_analysis` 可用 |
| 候选数为 0 / 过少 | §2.5 筛选 | 调 `min_event_length`/`min_seg_area_pe`/`asym_min`；确认 gain 使 PE 正确 |
| 匹配数异常 | §2.4 匹配 | 检查 `dynode_shift_ns`、`match_window_ns`、`channel_delay_ns` |
| dt 分布偏移 | §2.4 匹配 | 核对原始 dynode/anode 时间差与 +16 移位方向 |
| PE 值离谱 | §2.6 gain/PE | 确认 gain 后端与 run 是否匹配；`spe_gain` 列；`pe_fact` |
| 波形图不对 | §2.7 绘图 | 检查 dynode_scale / 反相 / 低通 cutoff；plot_len 是否截断 |
| 缓存误用/不一致 | §2.9 缓存 | `--clear-cache` 后重跑；确认参数哈希包含相关参数 |

诊断命令：
```bash
python -m pytest tests/                          # 单元测试
python -m pyflakes src/ scripts/ tests/          # 静态检查
python scripts/run_analysis.py --show-cache     # 查看缓存
python scripts/run_analysis.py --clear-cache     # 清缓存
```

---

## 6. 配置要点（config/analysis.yaml）

| 组 | 关键键 | 默认 | 说明 |
|---|---|---|---|
| matching | `dynode_shift_ns` | 16 | dynode 时间移位量(ns) |
| matching | `match_window_ns` / `min/max_diff_ns` | [0,30] | dt 匹配窗口 |
| matching | `sample_interval_ns` | 4 | 采样间隔(ns) |
| filtering | `asym_min` | 0.7 | 不对称度阈值 |
| filtering | `min_event_length` | 7000 | 最小波形长度 |
| filtering | `min_seg_area_pe` | 20000 | 最小段面积(PE) |
| features | `integral_window_mode` | fixed | fixed / peak_finder(预留) |
| features | `integral_start/end` | 20/100 | 固定积分窗口 |
| gain_db | `backend` | pmtdata | pmtdata/sqlite/csv |
| plotting | `dynode_scale` | 110 | dynode 放大倍数 |
| plotting | `dynode_lp_cutoff_hz` | null | compare 图 dynode 低通(如45e6) |
