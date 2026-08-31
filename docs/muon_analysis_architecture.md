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
                                  │ analyze_runs(单/多run, 并行, tqdm) / analyze_run(单run)
                                  ▼
   ┌─────────────────────────────────────────────────────────────────────────────┐
   │                              src/muon_analysis/                             │
   │                                                                             │
   │  ① config.py         配置加载/校验/覆盖(CLI>用户>默认) + 参数哈希 + YAML数值规范化│
   │  ② io/runinfo.py     runinfo.json 发现/解析 → RunInfo(含 raw_dir/runtype/mapping)│
   │  ③ io/readers*       读取records: waveform_analysis | npy | hdf5            │
   │     io/data.py        RunData(按board分离 dynode=1/anode=0)                  │
   │  ④ matching.py       时间匹配(移位 + merge_asof) ← 可缓存                    │
   │  ⑤ clustering.py     100ns 窗口聚类 → peaks(多 anode + 多 dynode) ← 可缓存   │
   │  ⑥ plotting/*        筛选前验证图(逐对+叠加) + 统计分布图                     │
   │  ⑦ features.py       peak 级特征(dynode ×110) + 积分窗口策略                    │
   │     gain.py           PMT SPE gain(pmtdata/sqlite/csv)                      │
   │     pe_calibration.py 电荷→PE(pe_fact/gain)                                  │
   │  ⑧ filtering.py      peak 级 muon 候选筛选(幅度/形状/PE 阈值)               │
   │  ⑨ cog.py            PMT pattern 导入 + COG(重心)位置重建                   │
   │  ⑩ track.py          dynode 1µs 时间切片 + 三维径迹重建                     │
   │  ⑪ output.py         CSV(peaks_id/cog_x/cog_y) / .npz / PNG / metadata      │
   │  ⑫ cache.py          /mnt/data/tmp/muon_analysis 缓存(run_id+参数哈希)      │
   └───────────────┬─────────────────────────────────────────────────────────────┘
                   │
                   ▼
       输出: <out-dir><run_id>/{events_run_<id>.csv, waveforms.npz, *.png, metadata.json}
```

数据流（单 run）：
`runinfo → read → match → cluster(peaks) → plot(验证) → features → filter → cog → track → output`

---

## 2. 各阶段处理细节与算法约定

### 2.1 配置与参数（config.py）
- 优先级：**CLI > 用户配置文件 > 内置默认**（`config/analysis.yaml`），`_deep_merge` 递归合并。
- `_normalize`：将 YAML 中以字符串形式出现的数值（如 `'45e6'`）统一转 float（`plotting.dynode_lp_cutoff_hz/cutoff_hz/fs`）。
- `param_hash(cfg)`：对处理参数做 SHA-1（排除输出/缓存等易变字段），用于缓存键与结果溯源。
- 配置分组：`matching`、`clustering`、`filtering`、`features`、`gain_db`、`plotting`、`cog`、`track`、`output`、`progress`。关键键见 [§6 配置要点](#6-配置要点)。

### 2.2 run 发现与信息（io/runinfo.py）
- `normalize_run_id`：补零到 5 位。
- `discover_runinfo_path`：`<data_root>/<runtype>/<rid>/runinfo.json`。
- **runtype 作用域/自动探测**：`runtype` 显式限定搜索路径；为空时 `discover_runtype` 扫描 data_root 下候选 runtype 目录（`run_R8520` / `run5_Ar` / `run6_Xe` 等）。`runinfo.runtype`（文件内）为权威值。
- 宽松校验：run_tag/datatype 不匹配时告警并置空 datatype，不阻断（适配 TPC/muon run）。
- `RunInfo` 携带 `raw_dir`（真实数据路径）、`mapping`（board/ch→pmt_id，供 COG/径迹使用）、`datatype` 等。

### 2.3 数据读取（io/readers*.py、io/data.py）
- 后端（`data_source.data_format`）：
  - `waveform_analysis_records`：`records_view(ctx, run_id)` 返回结构化 records（字段 `time, channel, board, record_id, event_length`）。
  - `npy` / `hdf5`：离线/中间持久化 records（可选波形 `*_waveforms.npy`）。
- `split_by_board`：`board==1 → dynode_records`，`board==0 → anode_records`，装入 `RunData`（含 `signals(ids)` 访问器）。
- 容错：单个 run 读取失败 → 打印 ERROR 并跳过，不中断批次。

### 2.4 时间匹配（matching.py）—— 关键算法
- **移位**：dynode 全局 `+dynode_shift_ns`（默认 **+6 ns**，`shift_time_records`，与实施计划/README 统一）。
- 逐通道延迟校准：按 `channel_delay_ns` 再对 dynode 附加偏移（可空）。
- **匹配**：pandas `merge_asof`，`by='channel'`、`direction='backward'`（每个 dynode 找 ≤ 它的最近 anode）。
- **窗口**：保留 `dt = t_dyn_shifted − t_ano ∈ [min_diff, max_diff] = [0, 40] ns`。
- 输出匹配表 `[dynode_idx, anode_idx, dt, channel]`（idx 为记录**位置索引**）；可缓存至 `/mnt/data/tmp/muon_analysis/<run_id>__<hash>_match.npy`。

### 2.5 波形聚类（clustering.py）【新增】
- `cluster_peaks(match_df, run_data, config)`：将匹配对按 dynode record time 聚合成 **peak**。
- **窗口**：`clustering.window_ns`（默认 **100 ns**），同一窗口内命中的所有通道（多 anode + 多 dynode）合入一个 peak（record time = 记录起始时间戳，仅作合并判据）。
- **Peak 模型**（models.py）：`peaks_id`、`start/end_time_ns`、`anode_records`/`dynode_records`（`PeakRecord`: record_id/channel/time_ns/is_dynode）、`match_rows`（匹配表行索引）、`channels`。
- **peak start/end（寻峰定义）**：`compute_peak_start_end`（pulsefinding.py）对 peak 内所有 anode+dynode 通道波形寻峰（**仅负脉冲**；dynode 波形先翻转），`peak.start = min(各通道 pulse_start)`、`peak.end = max(各通道 pulse_end)`（替换原 record-time min/max 定义）。
- **寻峰算法**：借鉴 `pmt_analysis.findpulse_st_ed`（pulsefinding.py）：基线扣除 → argmin → 有界 ±`search_range` 左右行走；阈值在 `config['pulse_finder']`（baseline_samples/height_threshold/search_range）。
- 输出：按时间排序、peaks_id 连续编号的 peak 列表；可缓存（`_peaks.json`，缓存加载后仍重算 start/end）。

### 2.6 候选筛选（filtering.py）
- **peak 级筛选（当前主流程）**：`filter_muon_candidates(peaks, peak_features, config)`，判据全部来自 `config["filtering"]`（None=不设限）：
  - 幅度：`height_min`/`height_max`（对 `peak_height`）；
  - 形状：`width_min`/`width_max`、`rise_time_max`；
  - PE：`min_area_pe_anode`/`min_area_pe_dynode`；
  - **已初步确定的物理判据（2026-08-17）**：`width_90area > 1000 ns` 且 `rise_time > 80 ns`（run 00183 筛出 2/1195）。
  - 输出 `MuonCandidate`（含 `passed_conditions` 逐判据记录）。
- **pair 级粗筛（legacy，保留）**：`filter_candidates`（asym 噪声剔除、`min_event_length`、`min_seg_area_pe`、高度阈值）供按匹配对分析的旧路径使用。

### 2.7 特征量 / PE 标定（features.py、gain.py、pe_calibration.py）
- **peak 级特征**：`compute_peak_features(peak, run_data, gain_db, config)`：
  - anode 记录：固定窗口积分（`integral_window_mode=fixed`，默认 [20,100)），负极脉冲；
  - **dynode 记录**：直接 **×`dynode_scale`（110）** 后积分——由于先放大波形，**area 也隐含 ×110**（满足需求）。**软件低通滤波已取消**（`dynode_lp_cutoff_hz=None`，新数据硬件已内置 25 MHz 低通电路）；**dynode 的寻峰（start/end）与特征均基于原始波形**（anode 亦用原始波形）；
  - 每记录 PE：`charge_to_pe(charge, gain)`（`pe_fact=(2/16384)*4e-9/(50*1.6e-19)/1e6`，`pe_calib=pe_fact/gain`）；
  - **rise_time**：`peak_index − pulse_start`（start→峰值点，样本；anode 取最负点、dynode 取最正点，两侧均计算）；
  - **面积占比宽度**：`width_90area`/`width_50area`（从 start 起累积 90%/50% 面积处的宽度，样本）；
  - **总电荷**：`area_ano`/`area_dyn`（anode/dynode 全通道电荷和，dynode 含 ×110）；
  - 聚合：`anode_area_pe`/`dynode_area_pe`（求和）、`peak_height`/`peak_width`/`peak_rise_time`/`width_90area`/`width_50area`（取通道最大）；
  - `charge_per_pmt`：按 `cog.charge_source`（anode|dynode）汇总各通道电荷，经 `runinfo.pmt_id_map[(board, ch)]` 映射为 pmt_id（供 COG 使用）。
- **积分窗口策略**：`IntegrationWindowResolver` 抽象，默认 `FixedWindowResolver`；预留 `PeakFinderWindowResolver`（待寻峰算法）。
- **gain**：`build_gain_db(config, run_id)` 按当前 run 查询；pmtdata 读 `spe_gain` 列，该 run 无条目时回退每通道最新值；sqlite/csv 后端按通道查。

### 2.8 可视化（plotting/waveforms.py、distributions.py、pattern.py）
- **筛选前验证图（peak 级，plan 模块五）**：
  - `plot_peak_pairs`：每个 peak 按通道**逐对绘制** anode（负极）+ dynode（低通 + 反相 ×110）；
  - `plot_peak_overlay`：两栏叠加——所有 anode 波形 / 所有 dynode 波形（低通 + ×110）。
  - 管线默认绘制前 `plotting.num_samples` 个 peak + `--plot-peaks` 指定序号。
- **PMT pattern 面积图**（`plotting/pattern.py`，参考 `xihu_fast_analysis/display.py` 约定）：
  - `plot_pmt_area_map(layout, charge_per_pmt, out_dir, run_id)`：按 PMT 坐标绘制旋转方块（30°、边长 21.5mm）+ 内外环（39/62mm），电荷 LogNorm viridis 着色（零电荷灰色），叠加 COG 红叉标记，坐标轴 mm、等比例。
  - 管线对前 `plotting.num_samples` 个候选 + `--plot-peaks` 指定候选生成（`pmt_area_run_<id>__<peaks_id>.png`）。
- `plot_by_record_id`：按 record_id 时间对齐绘制单对（`--plot-ids`）。
- `plot_distributions` / `plot_correlation` / 2D 直方：PE 谱、dt 谱、anode-dynode 相关、seg_area vs length（无 `channel` 列时自动退化为单色散点）。

### 2.9 COG 位置重建（cog.py）【新增，参考 layout.py 约定】
- **PMT 位置来源三级优先级**（`load_pmt_layout(config, runinfo)`，对齐 `xihu_fast_analysis/layout.py` 的 runinfo-first/fallback 行为）：
  1. 显式 pattern 文件（`cog.pattern_path`，JSON/CSV/YAML）；
  2. runinfo mapping 内嵌坐标（`mapping[].channels[].pos` → `[x, y]`，几何纯 2D 无 z）；
  3. 内置回退几何 `FALLBACK_ENTRIES`（7-PMT 参考布局，`cog.use_fallback=true` 启用）。
- **PmtLayout / PmtEntry** 数据模型：`pmt_positions_by_id`（pmt_id→(x,y)，可直接作 COG pattern）、`channels_by_board`、`entry_for_readout(board, ch)` 等查询。
- `cog_reconstruct(charge_per_pmt, pattern)`：重心法 `x_cog = Σ(w·x)/Σw`；仅用 pattern 中存在的 pmt，零权/缺失跳过。
- `cog_reconstruct_peak(features, runinfo, pattern, config)`：用 `features.charge_per_pmt` 计算事例横向位置。
- 管线中：layout 非空才启用；结果**回填事例 CSV 的 `cog_x`/`cog_y` 列**（与 record_id 同表）。

### 2.10 径迹重建（track.py）【新增】
- `slice_peak_waveforms(peak, run_data, config)`：将 peak 内各 dynode 波形（低通 + ×110）按 **`track.slice_us`（默认 1 µs）** 时间切片（`dt_ns = 1e9/fs`），输出各切片每通道电荷。
- `reconstruct_track(slice_data, runinfo, pattern, config)`：每切片通道电荷 → `pmt_id_map[(1, ch)]` → pmt_id → `cog_reconstruct` 得切片中心。
- `plot_track(track3d, out_dir, run_id)`：将所有切片中心（x, y, time）连接绘制**三维径迹** PNG（`track.save_plots` 可关）。

### 2.11 输出（output.py）
- 每 run 目录 `<out-dir><run_id>/`（run_id 补零，便于识别）。
- **事例级 CSV**（`peaks_to_dataframe` → `events_run_<id>.csv`），每行一个 muon 候选（peak）：
  `run_id, event_id, peaks_id, time_ns, channels, anode_record_ids, dynode_record_ids, anode_area_pe, dynode_area_pe, area_ano, area_dyn, peak_height, peak_width, peak_rise_time, peak_width_ns, width_90area, width_50area, cog_x, cog_y, parameter_version, gain_db_version`。
- `waveforms_*.npz`（每候选 anode/dynode 波形片段，可配置开关）、各 PNG、`run_<id>_metadata.json`。

### 2.12 缓存（cache.py）
- 目录 `/mnt/data/tmp/muon_analysis/`，键 `run_id + 参数哈希`；缓存**匹配表（.npy）与聚类 peaks（.json）**。
- `--show-cache` 列出（含来源溯源）、`--clear-cache` 清空；空间不足警告不自动清除。
- 注意：`waveform_analysis` 读取时在 `/tmp/v1725_parts_*` 分块暂存；多 run 并行可能冲突（见 §5 排查）。

---

## 3. 模块职责与代码位置对照

| 阶段 | 模块 | 关键函数 |
|---|---|---|
| 配置 | `config.py` | `build_config` / `param_hash` / `_normalize` |
| run信息 | `io/runinfo.py` | `get_runinfo` / `discover_runtype` |
| 读数据 | `io/readers.py` `io/readers_alt.py` `io/data.py` | `read_data` / `split_by_board` |
| 时间匹配 | `matching.py` | `match_events` / `get_matched_indices_by_channel` |
| 波形聚类 | `clustering.py` | `cluster_peaks` |
| peak 特征/PE | `features.py` `gain.py` `pe_calibration.py` | `compute_peak_features` / `build_gain_db` / `charge_to_pe` |
| peak 筛选 | `filtering.py` | `filter_muon_candidates`（legacy: `filter_candidates`） |
| 绘图 | `plotting/waveforms.py` `plotting/distributions.py` | `plot_peak_pairs` / `plot_peak_overlay` / `plot_distributions` |
| COG | `cog.py` | `load_pmt_layout` / `load_pmt_pattern` / `cog_reconstruct` |
| 径迹 | `track.py` | `slice_peak_waveforms` / `reconstruct_track` / `plot_track` |
| PMT 面积图 | `plotting/pattern.py` | `plot_pmt_area_map` |
| 输出 | `output.py` | `peaks_to_dataframe` / `save_events_csv` / `save_waveforms_npy` |
| 缓存 | `cache.py` | `read_npy` / `write_npy` / `show_cache` |
| 编排 | `pipeline.py` | `analyze_run` / `analyze_runs` |
| CLI | `scripts/run_analysis.py` `scripts/run_batch.py` | argparse / 批量驱动 |

---

## 4. 编排与并行（pipeline.py、scripts/run_batch.py）

- `analyze_run(run_id, config, out_dir)`：单 run 全流程
  `runinfo → read → match(缓存) → cluster(缓存) → 验证图 → features(tqdm) → filter → cog → track → output`，逐阶段 try/except；`RunReport` 统计 `total_events / matched_events / peak_count / passed_events / track_count`。
- `analyze_runs(run_ids, out_dir, ...)`：多 run 编排，`parallel=True` 时按 run 粒度 `ProcessPoolExecutor`；run 级与 peak 特征阶段使用 tqdm 进度条（`--no-progress` / `config.progress` 关闭）。
- CLI（run_analysis.py）：`run_id`（多/通配/`--run-list` 外部文件）、`--config`、`--data-root/--data-format/--runtype`、`--relaxed-filters`、`--gain-backend/--gain-path`、`--pattern`、`--out-dir`、`--no-save-waveforms/--no-save-plots`、`--plot-ids`（按 record_id）、`--plot-peaks`（按 peak 序号）、`--no-progress`、`--no-cache`、`--show-cache/--clear-cache`、`--parallel`、`--debug`。
- `scripts/run_batch.py`：批量驱动，**每 N 个 run 一组**（默认 3）、组内并行、内存/磁盘保护、断点续跑（已有输出跳过）、组级 tqdm。
- `scripts/sample_data.py`：离线示例数据生成（含 `--gain-db` SQLite 增益库、`--pattern` JSON pattern、runinfo mapping），阳极偏移 +6 ns 与匹配默认参数对齐。

---

## 5. 排查算法问题的路径

按"现象 → 定位阶段 → 检查项"排查：

| 现象 | 优先检查阶段 | 排查要点 |
|---|---|---|
| 读取失败 / `/tmp/v1725_parts_*` 缺失 | §2.3 读 | 并行度过高导致暂存冲突；改为串行/降并行度重试；确认 `waveform_analysis` 可用 |
| 匹配数为 0 / 过少 | §2.4 匹配 | 检查 `dynode_shift_ns`（默认 6）、`match_window_ns`（[0,40]）、`channel_delay_ns`；示例数据阳极需 +6 对齐 |
| peak 数异常 / 通道合并不合理 | §2.5 聚类 | 调 `clustering.window_ns`（100）；查看筛选前验证图（逐对/叠加）判断窗口是否过大/过小 |
| muon 候选为 0 / 过多 | §2.6 筛选 | 调 `height_min/max`、`width_min/max`、`rise_time_max`、`min_area_pe_anode/dynode`；确认 gain 使 PE 正确 |
| dynode 特征偏大/偏小 | §2.7 特征 | 核对 `dynode_scale`（110）；软件低通已取消（硬件 25 MHz 内置）；噪声大时核对硬件滤波/触发阈值 |
| PE 值离谱 | §2.7 gain/PE | 确认 gain 后端与 run 是否匹配；`spe_gain` 列；`pe_fact` |
| COG 为空（NaN）/ 位置不对 | §2.9 COG | 位置来源：pattern 文件（`cog.pattern_path`/`--pattern`）→ runinfo `mapping[].channels[].pos` → `cog.use_fallback` 回退几何；runinfo 需含 `mapping`（board/ch→pmt_id）；`charge_per_pmt` 非空；坐标单位约定（mm） |
| PMT 面积图异常 | §2.8 pattern 图 | 确认 layout 已加载（文件/runinfo/回退）；`charge_per_pmt` 的 pmt_id 与 layout 的 pmt_id 一致 |
| 径迹数为 0 / 切片异常 | §2.10 径迹 | 检查 `track.slice_us`（1 µs）、`fs`（250 MHz）；dynode 波形长度是否足够；mapping/pattern 与 COG 排查项相同 |
| 波形图不对 | §2.8 绘图 | 检查 dynode_scale / 反相 / 低通 cutoff；plot_len 是否截断；`--plot-peaks` 是否在范围内 |
| 缓存误用/不一致 | §2.12 缓存 | `--clear-cache` 后重跑；重新生成示例数据后需清缓存（键不含数据内容指纹）；确认参数哈希包含相关参数 |

诊断命令：
```bash
python -m pytest tests/                          # 单元测试（87 项）
python -m pyflakes src/ scripts/ tests/          # 静态检查
python scripts/run_analysis.py --show-cache     # 查看缓存
python scripts/run_analysis.py --clear-cache     # 清缓存
```

---

## 6. 配置要点（config/analysis.yaml）

| 组 | 关键键 | 默认 | 说明 |
|---|---|---|---|
| progress | `progress` | true | tqdm 进度条开关 |
| matching | `dynode_shift_ns` | 6 | dynode 时间移位量(ns)，与计划/README 统一 |
| matching | `match_window_ns` / `min/max_diff_ns` | [0,40] | dt 匹配窗口 |
| matching | `sample_interval_ns` | 4 | 采样间隔(ns) |
| clustering | `window_ns` | 100 | 波形聚类窗口（peak 合并，record time 判据） |
| pulse_finder | `baseline_samples` / `height_threshold` / `search_range` | 30/50/5 | 寻峰参数（负脉冲，dynode 先翻转；借鉴 findpulse_st_ed） |
| filtering | `height_min` / `height_max` | null | peak 级幅度上下限 |
| filtering | `width_min` / `width_max` | null | peak 级宽度上下限 |
| filtering | `rise_time_max` | null | peak 级上升时间上限 |
| filtering | `min_area_pe_anode` / `min_area_pe_dynode` | null | peak 级 PE 下限 |
| filtering | `min_event_length` / `min_seg_area_pe` / `asym_min` | 7000/20000/0.7 | legacy pair 级粗筛（保留） |
| features | `integral_window_mode` | fixed | fixed / peak_finder(预留) |
| features | `integral_start/end` | 20/100 | 固定积分窗口 |
| gain_db | `backend` | pmtdata | pmtdata/sqlite/csv |
| plotting | `dynode_scale` | 110 | dynode 放大倍数（幅度与 area 均 ×110） |
| plotting | `dynode_lp_cutoff_hz` | null | 软件低通截止(Hz)；**null=算法层不滤波**（硬件 25 MHz 已内置） |
| cog | `pattern_path` | "" | PMT pattern 文件路径；空则尝试 runinfo pos / 回退 |
| cog | `pattern_format` | auto | auto/json/csv/yaml |
| cog | `charge_source` | anode | 送入重心的电荷侧（anode/dynode） |
| cog | `use_fallback` | false | 无文件/runinfo pos 时启用内置 7-PMT 回退几何 |
| track | `slice_us` | 1.0 | 径迹时间切片宽度（µs） |
| track | `fs` | 250e6 | 采样率(Hz)，用于切片 |
| track | `save_plots` | true | 是否保存逐候选 3D 径迹 PNG |
| output | `cache_dir` | /mnt/data/tmp/muon_analysis | 缓存根目录 |
