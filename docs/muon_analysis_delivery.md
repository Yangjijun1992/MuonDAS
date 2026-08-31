# Muon 分析工具 - 交付内容

> 本文档记录当前已完成的交付内容，用于后续排查开发流程的完善情况。
> 配套文档：[需求规格](muon_dynode_analysis_requirements.md)、[实施计划与任务清单](muon_dynode_analysis_implementation_plan.md)、
> [架构总览](muon_analysis_architecture.md)、[开发进展与后续开发](muon_development_progress.md)。

**状态**：核心功能全部完成（96 项 pytest 通过，pyflakes 无告警，CLI 顺序/并行端到端可运行；
合成数据与**真实数据（run 00179）**全流程跑通）。

---

## 项目结构

```
MuonDAS/
├── config/                            # YAML 参数配置
│   ├── analysis.yaml                  # 全部可调参数（匹配/聚类/筛选/特征/gain/绘图/COG/径迹/输出）
│   └── data_source.yaml               # 数据根目录/runtype
├── src/muon_analysis/                 # 核心包（模块化）
│   ├── config.py                      # 配置加载/校验/数值规范化/默认值/参数哈希
│   ├── models.py                      # RunInfo、Peak、PeakFeatures、MuonCandidate 数据模型
│   ├── matching.py                    # 打拿极-阳极时间匹配（移位 + merge_asof）
│   ├── clustering.py                  # 100ns 窗口波形聚类 → peaks（多 anode + 多 dynode）
│   ├── features.py                    # peak 级特征（dynode ×110）+ 积分窗口策略
│   ├── gain.py                        # PMT SPE gain 数据库（pmtdata/sqlite/csv）
│   ├── pe_calibration.py              # 电荷 -> PE 换算
│   ├── filtering.py                   # peak 级 muon 候选筛选（legacy pair 级粗筛保留）
│   ├── cog.py                         # PMT pattern 导入（文件/runinfo pos/回退）+ COG 重建
│   ├── track.py                       # dynode 1µs 时间切片 + 三维径迹重建
│   ├── cache.py                       # /mnt/data/tmp/muon_analysis 缓存管理
│   ├── output.py                      # CSV（含 peaks_id/cog_x/cog_y）/ NPY / PNG 持久化
│   ├── pipeline.py                    # 主流程编排（peak 流程）+ tqdm + 多进程
│   └── io/
│   │   ├── runinfo.py                 # runinfo.json 解析/真实路径调取/runtype 自动探测
│   │   ├── readers.py                 # waveform_analysis 后端读取
│   │   ├── readers_alt.py             # npy / hdf5 后端读取
│   │   ├── run_index.py               # run_id 解析（列表/通配/外部文件）
│   │   └── data.py                    # RunData（按 board 分离 dynode=1/anode=0）
│   └── plotting/
│       ├── waveforms.py               # 波形可视化（逐对/叠加验证 + 时间对齐）
│       ├── distributions.py           # 统计分布图（PE 谱/dt 谱/相关/2D 直方）
│       └── pattern.py                 # PMT 面积图（布局方块 + 电荷着色 + COG 标记）
├── scripts/
│   ├── run_analysis.py                # 命令行入口
│   ├── run_batch.py                   # 批量驱动（分组/并行/内存磁盘保护/断点续跑/tqdm）
│   └── sample_data.py                 # 离线示例数据生成（含增益库/pattern 生成）
├── tests/                             # pytest 单元测试（96 项）
├── docs/                              # 需求 / 计划 / 架构 / 交付 / 进展 / 报告
├── examples/                          # 参考实现（raw_reader/runinfo/pipeline/ipynb）
└── README.md
```

## 模块清单与功能

### 模块1 - 配置与命令行（config / CLI）
- `config.py`：加载 `analysis.yaml`，覆盖优先级 **CLI > 用户配置 > 默认值**；`_validate` 校验；`_normalize` 将 YAML 字符串数值（如 `'45e6'`）转 float；`param_hash` 参数哈希（排除易变字段）。
- 配置分组：`matching` / `clustering` / `filtering` / `features` / `gain_db` / `plotting` / `cog` / `track` / `output` / `progress`。
- `scripts/run_analysis.py`：支持多 run_id、`--run-list`（外部文件）、`--config`、`--data-root/--data-format/--runtype`、`--relaxed-filters`、`--gain-backend/--gain-path`、`--pattern`、`--out-dir`、`--no-save-waveforms/--no-save-plots`、`--plot-ids`（按 record_id）、`--plot-peaks`（按 peak 序号）、`--no-progress`、`--no-cache`、`--show-cache/--clear-cache`、`--parallel`、`--debug`。

### 模块2 - 数据读取（io）
- `get_runinfo`：runtype 显式限定 / 自动探测；`run_info.runtype` 为权威；宽松校验（run_tag/datatype 不匹配降级警告不阻断）。
- `read_data`：`waveform_analysis_records` / `npy` / `hdf5` 三后端；`split_by_board` 分离 dynode/anode。
- `run_index.py`：列表 / 通配符（glob）/ 外部配置文件三种 run_id 传入方式。
- 容错：单 run 失败打印 ERROR 跳过，不中断批次。

### 模块3 - 时间匹配（matching）
- `shift_time_records`：dynode 全局 `+dynode_shift_ns`（默认 **6 ns**，与计划/README 统一）。
- `get_matched_indices_by_channel`：pandas `merge_asof` 按 channel（`direction='backward'`）。
- 窗口 `dt ∈ [0, 40] ns`；支持逐通道延迟校准 `channel_delay_ns`。

### 模块4 - 波形聚类（clustering → peaks）【新增】
- `cluster_peaks(match_df, run_data, cfg)`：按 dynode record time 以 `clustering.window_ns`（默认 100 ns）聚合成 `Peak`。
- `Peak` 模型：`peaks_id`、时间范围、anode/dynode 记录列表（record_id/channel/time）、`match_rows`、`channels`。
- 可缓存（`_peaks.json`）。

### 模块5 - 波形可视化与验证（筛选前）【重排】
- `plot_peak_pairs`：peak 内逐对绘制 anode/dynode。
- `plot_peak_overlay`：两栏叠加（所有 anode / 所有 dynode）。
- 管线默认绘制前 `num_samples` 个 peak + `--plot-peaks` 指定序号，作为**筛选前验证步骤**。

### 模块6 - 事例特征分析（含 dynode 滤波/放大 与 PE）
- `compute_peak_features`：anode 负极固定窗口积分；**dynode 直接 ×110 放大后积分（area 隐含 ×110）；软件低通已取消（硬件 25 MHz 内置）**；每记录 PE 换算；peak 级聚合 area/height/width/rise_time；`charge_per_pmt`。
- 积分窗口策略接口 `IntegrationWindowResolver`（fixed 默认 / peak_finder 预留寻峰）。
- gain：pmtdata/sqlite/csv 后端，按当前 run 查询，无条目回退每通道最新值。

### 模块7 - muon 事例筛选（peak 级）
- `filter_muon_candidates(peaks, peak_features, cfg)`：幅度（height_min/max）、形状（width_min/max、rise_time_max）、PE（min_area_pe_anode/dynode）判据，全部配置化，None=不设限；输出 `MuonCandidate`（含 `passed_conditions`）。
- legacy pair 级粗筛 `filter_candidates`（asym/长度/段面积）保留供旧路径使用。

### 模块8 - 结果输出
- 事例级 CSV（`peaks_to_dataframe`）：`run_id / event_id / peaks_id / time_ns / channels / anode_record_ids / dynode_record_ids / anode_area_pe / dynode_area_pe / peak_height / peak_width / peak_rise_time / cog_x / cog_y / parameter_version / gain_db_version`。
- 波形片段 `.npz`（可配置开关）；统计分布 `.png`；运行元数据 JSON；输出目录自动创建。

### 模块9 - 缓存管理与数据溯源
- 缓存根目录 `/mnt/data/tmp/muon_analysis/`；键 `run_id + param_hash`；缓存**匹配表（.npy）与聚类 peaks（.json）**。
- `--show-cache`（含条目溯源）/ `--clear-cache`；空间不足警告不自动清除。

### 模块10 - PMT pattern 导入与 COG 位置重建【新增】
- `load_pmt_layout` 三级优先级：**pattern 文件（JSON/CSV/YAML）→ runinfo mapping `channel["pos"]` → 内置 7-PMT 回退几何（`cog.use_fallback`）**（对齐 `xihu_fast_analysis/layout.py` 约定）。
- `PmtEntry`/`PmtLayout` 数据模型：`pmt_positions_by_id`、`channels_by_board`、`entry_for_readout`。
- `cog_reconstruct` 重心法；结果回填 CSV `cog_x`/`cog_y` 列（与 record_id 同表）。

### 模块11 - muon 径迹重建【新增】
- `slice_peak_waveforms`：dynode 波形（×110）按 `track.slice_us`（默认 1 µs）切片。
- `reconstruct_track`：每切片通道电荷 → pmt_id（`pmt_id_map[(1, ch)]`）→ 重心法切片中心。
- `plot_track`：切片中心（x, y, time）连成三维径迹 PNG（采样绘制）。

### 模块12 - 主流程编排与多进程（pipeline + CLI）
- 单 run 流程：`read → match(缓存) → cluster(缓存) → 验证图 → features(tqdm) → filter → COG → CSV → track/面积图 → 分布图`。
- `RunReport` 统计 `total_events / matched_events / peak_count / passed_events / track_count`。
- `analyze_runs`：并行（`ProcessPoolExecutor`）+ tqdm 进度条；`run_batch.py`：分组/并行/内存磁盘保护/断点续跑。

### 模块13 - 测试与文档
- `tests/`：96 项 pytest，覆盖 io/matching/clustering/plotting/features/gain/pe_calibration/filtering/output/cache/cog/track + pipeline 端到端（含 COG/径迹链路）。
- `README.md`（用法/离线示例）、`config/*.yaml` 注释、架构/进展文档。

## 真实数据验证（run 00179，run6_Xe）

- 读取真实 V1725 数据（`waveform_analysis` 后端，`pmtdata` 增益）→ **matched=214,515** → **peaks=30,645**（每 peak 恒 7 通道，符合 7-PMT 探测器）→ 候选 30,645（默认阈值全 None，未筛选）。
- **COG**：30,645/30,645 填充；runinfo `mapping[].channels[].pos` 坐标生效（真实 mapping 结构 `ch/pmt/pos/label` 与参考布局完全一致，如 ch15=LV2389@(-26.8,17.7)）；COG 径向分布 r 均值 3.1mm（7 通道近等权 → 重心趋中，物理合理）。
- **径迹**：30,645 条重建（dynode 1µs 切片）。
- 产物：`events_run_00179.csv`、`waveforms_run_00179.npz`、验证图（逐对/叠加）、PMT 面积图、径迹采样图、分布图。

## 已知限制 / 待完善（排查项，详见 [开发进展](muon_development_progress.md)）

- [ ] **dynode_area_pe 在真实数据上为负**（均值 -190）：积分未减基线（真实 ADC 基线偏移），需基线修正（P0）。
- [ ] **筛选阈值默认全部 None**：30645 候选全部通过，需按真实物理预期标定（P1）。
- [ ] **交互式缩放/平移**（需求 §4 字面项）：当前仅保存静态 PNG，未实现（P1）。
- [ ] 计划接口偏差：`features.dynode_*` 分组实际在 `plotting` 分组；缓存键未含 `gain_db_version`；`--debug` 未接线（P2）。
- [ ] hdf5 后端无测试覆盖；特征结果未缓存（P2）。
- [ ] 寻峰算法接口已预留（`PeakFinderWindowResolver`），待用户提供算法接入。

## 快速自检命令

```bash
# 单元测试
python -m pytest tests/

# 静态检查
python -m pyflakes src/ scripts/ tests/

# 离线端到端（示例数据，含 COG/径迹）
python scripts/sample_data.py --run-id 00179 --out /tmp/muon_demo \
    --gain-db /tmp/muon_demo/gains.db --pattern /tmp/muon_demo/pattern.json
python scripts/run_analysis.py 00179 --data-root /tmp/muon_demo --data-format npy \
    --relaxed-filters --gain-backend sqlite --gain-path /tmp/muon_demo/gains.db \
    --pattern /tmp/muon_demo/pattern.json

# 真实数据（自动探测 runtype，pmtdata 增益，runinfo pos 坐标）
python scripts/run_analysis.py 00179 --out-dir /tmp/mm_out

# 缓存管理
python scripts/run_analysis.py --show-cache
python scripts/run_analysis.py --clear-cache
```
