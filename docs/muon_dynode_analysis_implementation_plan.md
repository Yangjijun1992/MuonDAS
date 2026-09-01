# Muon 事例筛选、打拿极读出分析与径迹重建 分模块实施计划与任务清单

> 配套文档：[需求规格](./muon_dynode_analysis_requirements.md)
>
> 本计划将系统按新算法流程拆分为多个高内聚、低耦合模块。每个模块含目标、接口约定与可勾选任务清单。
>
> **处理流程**：数据读取 → 时间匹配 → 波形聚类(peaks) → 波形可视化与验证 → 事例特征分析 → muon 事例筛选 → 结果输出 → PMT pattern + COG 位置重建 → muon 径迹重建。
>
> **基准实现（reference）**：读取/匹配/面积/PE/绘图约定对齐示例代码：`raw_reader.py`、`runinfo.py`、`pipeline.py`、`dynode_large_pulse_selection.ipynb`。PMT pattern 与 COG 位置重建复用已有成熟脚本。

---

## 0. 总体架构与目录结构

采用 `src/` + `scripts/` + `config/` + `output/` 的典型 Python 工程布局。

```
MuonDAS/
├── docs/                        # 需求、实施计划、架构、报告等
├── config/
│   ├── analysis.yaml            # 全部可调参数（聚类窗口、滤波/放大、筛选、pattern 等）
│   └── data_source.yaml         # 数据目录、文件格式、通道延迟校准、gain 与 pattern 库路径
├── src/muon_analysis/
│   ├── __init__.py
│   ├── config.py                # 配置加载/校验/默认值/参数哈希
│   ├── io/
│   │   ├── __init__.py
│   │   ├── readers.py           # waveform_analysis / npy / hdf5 读取
│   │   ├── run_index.py         # run_id 解析
│   │   ├── runinfo.py           # runinfo.json 解析、真实路径调取
│   │   └── data.py              # RunData（按 board 分离 dynode/anode）
│   ├── matching.py              # 打拿极-阳极时间对齐（移位 + merge_asof）
│   ├── clustering.py            # 波形聚类：100ns 内聚合成 peaks（多 anode + 多 dynode）
│   ├── features.py              # peak 级特征量（charge/height/上升沿/宽度）+ dynode 低通/放大
│   ├── gain.py                  # PMT SPE gain 数据库
│   ├── pe_calibration.py        # 电荷 -> PE
│   ├── filtering.py             # muon 候选事例筛选（可视化验证之后）
│   ├── plotting/
│   │   ├── __init__.py
│   │   ├── waveforms.py         # 可视化（验证）：逐对 + anode 叠加 + dynode 叠加
│   │   └── distributions.py     # 特征统计分布图
│   ├── cog.py                   # PMT pattern 导入 + COG 位置重建
│   ├── track.py                 # 基于 dynode 波形的时间切片 + 重心法三维径迹重建
│   ├── cache.py                 # /mnt/data/tmp/muon_analysis 缓存管理
│   ├── output.py                # CSV / .npy 结果持久化
│   └── pipeline.py              # 主流程编排
├── scripts/
│   ├── run_analysis.py          # 命令行入口
│   ├── run_batch.py             # 批量驱动（分组/并行/内存保护/断点续跑）
│   └── sample_data.py           # （可选）模拟数据
├── tests/                       # pytest 单元测试
└── output/                      # 默认输出目录（CSV/PNG/NPY）
```

**技术决策**

- Python 3.10+，依赖：NumPy、SciPy、Matplotlib、PyYAML、pandas、h5py。
- 通道约定：`board == 1` 为 dynode，`board == 0` 为 anode。
- 聚类时间窗默认 100 ns（可配置 `clustering.window_ns`）。
- dynode 特征分析前置：无软件低通（硬件 25 MHz 内置）+ **×113 放大**（dynode_scale）；
  `dynode_sum`/逐通道 dynode 特征/`dynode_sum_area` ×113；`area_dyn`/`dynode_area_pe` 基于原始 ×1（写入配置）。
- 缓存根目录：`/mnt/data/tmp/muon_analysis/`（含缓存追踪与来源溯源）。所有缓存与分析产生的输出统一保存于该路径下。
- 性能：NumPy 向量化 + 可选 `multiprocessing`/`concurrent.futures` 并行按 run/peak 处理。

---

## 1. 模块一：配置与命令行接口（config / CLI）

**目标**：集中管理所有可调参数（含聚类窗口、dynode 滤波/放大、筛选、pattern、切片等）；提供清晰命令行接口。

**接口约定**

- 配置为 YAML，支持 CLI 覆盖关键项。新增分组：`clustering`、`features.dynode_lp`/`features.dynode_scale`、`cog`、`track`。
- CLI 参数（argparse）：`run_id`（多/通配符，或 `--run-list <file>` 外部配置文件）、`--config`、`--data-root/--data-format/--runtype`、`--out-dir`、`--gain-backend/--gain-path`、`--no-save-waveforms`、`--no-save-plots`、`--plot-ids`（按 record_id 绘制）、`--plot-peaks`（按 peak/事例序号绘制）、`--clear-cache`、`--show-cache`、`--parallel`、`--debug`。

**任务清单**

- [ ] config 数据模型与默认值：匹配窗口 `[0,40]`、`dynode_shift_ns=16`（No-Field）/4（00183）、聚类 `window_ns=100`、特征积分窗口、dynode 低通 cutoff=null/scale=230、筛选阈值、`cog`/`track` 参数、`cache_dir=/mnt/data/tmp/muon_analysis`。
- [ ] YAML 加载、覆盖（CLI > 用户配置 > 默认）与校验。
- [ ] `analysis.yaml` 完善（含 `clustering`、`features.dynode_*`、`cog`、`track` 默认值）。
- [ ] `scripts/run_analysis.py` argparse 解析与帮助文本。
- [ ] `--run-list <file>` 外部配置文件方式读取 run_id 清单（每行一个 run_id，与命令行列表/通配符并列，覆盖需求 §1）。
- [ ] 配置版本号 `parameter_version`（用于可重复性与缓存哈希）。
- [ ] （联调）默认示例 `config/*.yaml`。

---

## 2. 模块二：数据读取（io）

**目标**：批量解析多 run 的 dynode/anode 数据，容错跳过坏 run，提供记录/波形访问。

**接口约定**

- `get_runinfo(run_id, data_root, runtype,...) -> RunInfo`（含 runtype 自动探测、宽松校验）。
- `read_data(runinfo, fmt, data_dir) -> RunData`（`waveform_analysis` / `npy` / `hdf5`；`board==1` dynode、`==0` anode）。
- `RunData.signals(record_ids)`：按 record_id 取波形访问器。

**任务清单**

- [ ] 移植/封装 `runinfo.py`、`raw_reader.py`（含 runtype 发现/作用域、容错跳过）。
- [ ] 按 `board` 分离 dynode/anode records。
- [ ] npy/hdf5 可选读取器 + `RunData` 容器。
- [ ] 单元测试：读取与容错。

---

## 3. 模块三：时间匹配（matching）

**目标**：dynode/anode 高精度时间对齐，输出配对事件列表供聚类阶段使用。

**接口约定**

- `match_events(run_data, cfg) -> DataFrame[dynode_idx, anode_idx, dt, channel]`。
- dynode 移位 `dynode_shift_ns`（默认 6 ns，可配置）+ 按 channel `merge_asof` + `dt∈[0,40]` 窗口；逐通道延迟校准 `channel_delay_ns`。匹配默认参数统一以本计划为准（`dynode_shift_ns=6`、`dt∈[0,40]`，README 已同步更新）。
- 匹配结果可缓存（见模块九）。

**任务清单**

- [ ] `shift_time_records`（配置驱动移位量）。
- [ ] `get_matched_indices_by_channel`（merge_asof + dt 窗口）。
- [ ] 参数集中配置；输出匹配表。
- [ ] 单元测试：已知偏移验证对齐。

---

## 4. 模块四：波形聚类（clustering → peaks）【新增】

**目标**：将时间匹配后、同一事件的多通道波形按时间聚合成 **peak**，供可视化与特征/筛选使用。

**接口约定**

- `cluster_peaks(match_df, run_data, cfg) -> list[Peak]`：
  - 将 **record time 在 `window_ns`（默认 100 ns）范围内**的所有波形聚合成一个 `Peak`。
  - 每个 `Peak` 含**多个 anode 通道波形**与**多个 dynode 通道波形**（同窗内命中的所有通道），各自 `record_id`/`channel`/`time`。
  - 每个 `Peak` 分配 `peaks_id`。
- `Peak` 数据模型：`peaks_id`、时间范围（start/end）、anode 记录列表（record_id/ch）与 dynode 记录列表。
- **peak 时间范围（start/end）定义（修订）**：
  - 对 peak 内所有 anode 与 dynode 通道波形分别**寻峰**，得各通道脉冲边界 `pulse_start`/`pulse_end`；
  - `peak.start` = 所有通道 `pulse_start` 的最小值，`peak.end` = 所有通道 `pulse_end` 的最大值；
  - 寻峰算法为**独立可插拔模块**（`pulse_finder` 接口），算法本体由用户后续提供并接入。

**任务清单**

- [x] 设计 `Peak` 数据模型（含 peaks_id、所占通道集合、波形记录索引、时间窗）。
- [x] 实现按时间窗（默认 100 ns）对匹配记录聚类成 peak 的算法（record time 合并判据）。
- [x] **定义寻峰接口 `pulse_finder`**：输入单通道波形，输出 `(pulse_start, pulse_end)`（样本索引或时间）；anode/dynode 通用（**仅负脉冲**，dynode 波形由调用方先翻转）；默认实现借鉴 `pmt_analysis.findpulse_st_ed`（有界 ±search_range 寻峰）。
- [x] **peak start/end 重算**：`compute_peak_start_end` 对 peak 内所有 anode+dynode 通道波形调用寻峰（dynode 翻转）→ 各通道 `pulse_start/end` → `peak.start = min(...)`、`peak.end = max(...)`（已替换原"record time min/max"定义；真实 run 00183 验证：窗口与脉冲对齐，1195 个 7 通道 peak 窗口宽中位数 44ns）。
- [ ] **寻峰算法接入**：默认实现已落地（借鉴 findpulse_st_ed）；用户自定义寻峰算法可后续替换 `pulse_finder` 实现（`config['pulse_finder']` 阈值可调）。
- [x] peak 聚类窗口参数写入配置（`clustering.window_ns`）。
- [x] 输出 peak 列表（供可视化、特征、筛选）。
- [x] 单元测试：构造多通道时间邻近事件验证聚类正确性；寻峰边界聚合测试（构造已知脉冲位置波形验证 peak.start/end）。

---

## 5. 模块五：波形可视化与验证（在筛选之前）【重排】

**目标**：在筛选**之前**可视化每个 peak，快速检查 peaks 内波形与通道合并是否合理。

**接口约定**

- `plot_peak_pairs(peak, run_data, out_dir)`：将每个 peak 中**所有 anode/dynode 通道对**逐一绘制。
- `plot_peak_overlay(peak, run_data, out_dir)`：
  - 将所有 **anode** 波形叠加显示；
  - 将所有 **dynode** 波形叠加显示。
- 支持交互式缩放/平移；保存 `.png`；支持自动批量或指定 peak 序号。

**任务清单**

- [ ] 逐对绘制（peak 内所有 anode/dynode 对）。
- [ ] anode 叠加图、dynode 叠加图。
- [ ] 交互缩放/平移；`.png` 保存与批量/指定绘制（CLI `--plot-peaks` 按 peak/事例序号绘制，区别于 `--plot-ids` 按 record_id）。
- [ ] 输出作为筛选前验证步骤。

---

## 6. 模块六：事例特征分析（对合并后的 peaks，含 dynode 滤波/放大 与 PE 标定）

**目标**：对每个合并后的 peak 波形计算特征量（charge/height/上升沿/宽度），并按 PMT gain 换算 PE。dynode 部分无软件低通 + ×113 放大（`dynode_sum` 逐通道先 ×113 再对齐求和；`area_dyn` 基于原始 ×1）。

**接口约定**

- `compute_peak_features(peak, run_data, cfg) -> PeakFeatures`：
  - 对 peak 内 anode 与 dynode 波形分别计算 area/height/rise_time/width。
  - **dynode 处理**：无软件低通（硬件 25 MHz 内置）；每个 dynode 通道 ×113 后参与 `dynode_sum` 求和；`area_dyn`/`dynode_area_pe` 用原始 ×1 的 `dynode_sum_raw`。
- `compute_integral_pe` / 积分窗口策略（固定窗口，预留寻峰）；`pe_fact/gain` 按通道换算 PE。
- `GainDB`（pmtdata/sqlite/csv，**沿用现有读取方式，不新增后端**）按通道查增益。
- **寻峰关联**：特征积分窗口的起始点定位（`PeakFinderWindowResolver` 预留接口）与 peak start/end 计算（模块四 `pulse_finder`）共用同一寻峰算法/接口，由用户提供后统一接入。

**任务清单**

- [x] 特征量计算（面积、峰高、上升沿 10-90%、半高宽/宽度）。
- [x] **rise_time 定义（修订）**：`peak_index − pulse_start`（start→峰值点）；anode 负脉冲取最负点、dynode 取最正点，两侧均计算；`width`/`rise_time`/`width_90area`/`width_50area` 均 ×4ns → 以 **ns** 计。
- [x] **peak 级参数统一由 sum 波形计算（修订 2026-08-31）**：`anode_sum`/`dynode_sum`（各通道按 pulse_start 对齐逐点求和；dynode 每通道先 ×113 再叠加）→ `height`（sum 高度）、`width`/`rise_time`（anode_sum）、`width_ns`（sum 脉冲时长）、`width_90area`/`width_50area`（anode_sum 面积占比）均由 sum 波形计算；命名去掉 `peak_`/`sum_` 前缀（`peak_height→height` 等）。
- [x] **面积参数重定义**：`area_ano`/`area_dyn` = anode_sum/dynode_sum_raw（原始 ×1）在 **[anode_sum start, dynode_sum end]** 区间的面积；`anode_area_pe`/`dynode_area_pe` = 同区间 × mean-gain 的 PE（无放大）；`anode_sum_area`/`dynode_sum_area` = sum 全波形 × mean-gain 的 PE（dynode 侧含 ×113）。
- [x] **peak 级总电荷**：`area_ano`/`area_dyn`（sum 波形区间面积，dynode 原始 ×1）。
- [x] dynode 软件低通滤波（已取消：新数据硬件内置 25 MHz 低通，算法层不滤波）。
- [x] dynode 放大 **×113**（`dynode_scale`；逐通道先放大再 sum；`dynode_sum_area`/逐通道特征 ×113，`area_dyn` ×1）。
- [x] 固定窗口积分策略 + 预留寻峰接口；PE 换算（mean-gain）。
- [x] 生成特征统计分布图（PE 谱、时间差谱、width_90area/width_50area 直方图与 2D 图）验证聚类/筛选合理性，保存 `.png`。

---

## 7. 模块七：muon 事例筛选（在可视化验证之后）

**目标**：在波形可视化验证与特征分析之后，根据 peak 级特征设置筛选条件，判定 muon 候选事例。

**接口约定**

- `filter_muon_candidates(peaks, peak_features, cfg) -> list[MuonCandidate]`。
- 判据基于：幅度阈值、时间符合/聚类窗口、脉冲形状（area/height/width/rise_time）、PE 相关阈值。
- 所有筛选参数集中配置文件。

**任务清单**

- [ ] 设定 muon 筛选判据（阈值/窗口/形状，基于 peak 特征）。
- [ ] 参数全部配置文件化。
- [ ] 输出 muon 候选事例集合（含 peaks_id、通道、各 record_id）及筛选通过属性。
- [ ] 单元测试：正/负例验证筛选正确性。

---

## 8. 模块八：结果输出【含 record_id 等】

**目标**：保存 muon 事例信息（peak 级参数、peaks_id、pmt_id、anode/dynode record_id）及波形片段、统计图。

**接口约定**

- `save_muon_csv(candidates, ...)`：每行含 run_id、event_id、`peaks_id`、`pmt_id`、anode/dynode `record_id`、peak 级 area/height/width、PE、time、COG 重建位置（`cog_x`/`cog_y`，由模块十回填、与 `record_id` 对应）、溯源列（parameter_version / gain_db_version）。
- `save_waveforms_npy(...)`：波形片段 `.npy`（可开关）。
- 统计图 `.png` 保存至指定目录。

**任务清单**

- [ ] CSV 输出含 **peaks_id、各 pmt_id 的 anode/dynode record_id、peak 级参数**（area/height/width）与溯源列。
- [ ] 事例 CSV 预留并回填 `cog_x`/`cog_y` 列（衔接模块十 COG 重建）。
- [ ] 全通道波形片段 `.npy`（可配置）。
- [ ] 统计分布图 `.png`。
- [ ] 输出目录自动创建、按指定路径落盘。

---

## 9. 模块九：缓存管理与数据溯源

**目标**：中间数据（匹配结构、peak 结构、特征结果）缓存至 **`/mnt/data/tmp/muon_analysis/`**；所有缓存文件及分析过程中产生/输出的信息统一保存于该路径；缓存追踪与来源溯源也从该路径进行。

**接口约定**

- `cache_path(run_id, param_hash) -> /mnt/data/tmp/muon_analysis/<run_id>_<hash>.<ext>`。
- `param_hash = sha1(处理参数) + gain_db_version`。
- CLI：`--clear-cache` 清空该目录；`--show-cache` 列出条目及对应原始数据标识（来源追踪）。
- 缓存空间不足警告（不自动清除）。

**任务清单**

- [ ] 缓存根目录默认改为 `/mnt/data/tmp/muon_analysis/`（config/config.py/cache.py 已改）。
- [ ] 缓存 key 哈希（run_id + 处理参数 + gain 版本）。
- [ ] 缓存读写（匹配、peak 聚类、特征等中间结构）。
- [ ] `--show-cache`（含来源溯源）/ `--clear-cache`。
- [ ] 空间不足警告；缓存追踪从新路径进行。
- [ ] 单元测试：哈希一致 / 命中 / 清除。

---

## 10. 模块十：PMT pattern 导入与 COG 位置重建【新增】

**目标**：导入 pmt pattern 信息，用于 COG（重心）位置重建，复用成熟脚本。

**接口约定**

- `load_pmt_pattern(path) -> Pattern`：PMT_id → 空间位置 (x,y[,z])。
- `cog_reconstruct(charge_per_pmt, pattern) -> (x_cog, y_cog)`：重心法计算事件横向位置。

**任务清单**

- [ ] 复用/封装成熟 pmt pattern 脚本，导入 pattern。
- [ ] COG 重心法实现。
- [ ] 对每个 muon 事例输出重建位置（回填至事例 CSV 的 `cog_x`/`cog_y` 列，与 `record_id` 对应）。
- [ ] 单元测试：已知电荷/pattern 验证重心位置。

---

## 11. 模块十一：muon 径迹重建【新增】

**目标**：依据筛选出 muon 事例的 dynode 波形重建三维径迹（时间切片 + 重心法 + 连线）。

**接口约定**

- `slice_peak(peak, slice_us=1.0) -> list[slice]`：将 dynode 合并后的 peak 级波形按 **1 µs 一个时间切片**切分。
- `reconstruct_track(track_slices, pattern) -> Track3D`：
  - 每个切片内所有 PMT 的 charge 赋给各自 `pmt_id`；
  - 依据 pmt pattern 用**重心法**重建每个切片位置中心；
  - 将所有切片中心连接，画出**三维径迹**。

**任务清单**

- [ ] dynode peak 波形时间切片（1 µs）。
- [ ] 每切片所有 PMT charge → 对应 pmt_id。
- [ ] 结合 pmt pattern 用重心法重建每切片位置中心。
- [ ] 切片中心串联，绘制三维径迹（三维图/曲线）。
- [ ] 单元测试：合成切片数据验证重心与径迹。

---

## 12. 模块十二：主流程编排与多进程（pipeline + CLI）

**目标**：串联 runinfo→ 读取 → 匹配 → 聚类 → 可视化验证 → 特征 → 筛选 → 输出 →COG→ 径迹；进度统计；可选并行。

**接口约定**

- `analyze_run(run_id, cfg, out_dir) -> RunReport`；`analyze_runs(...)`（`--parallel`）。
- `scripts/run_batch.py`：批量驱动（每 N 个一组、并行、内存/磁盘保护、断点续跑）。

**任务清单**

- [ ] 主流程：read → match → cluster → plot(验证) → features → filter → output → cog → track。
- [ ] 每阶段缓存命中短路；进度条（tqdm）与关键统计（总事件、peak 数、候选数、径迹数）。
- [ ] 按 run `try/except` 容错；多进程并行（可选）。
- [ ] `scripts/run_analysis.py` 完整接线。

---

## 13. 模块十三：测试与文档

**目标**：可维护性/可重复性验证。

**任务清单**

- [ ] pytest 覆盖 io/matching/clustering/plotting/features/gain/pe_calibration/filtering/output/cache/cog/track。
- [ ] 运行说明（README/usage）与配置文件注释。
- [ ] 示例数据生成脚本 `scripts/sample_data.py`。

---

## 14. 依赖关系与建议实施顺序

```
config/CLI (1)
  └─ io (2)
       └─ matching (3) ──► clustering (4)
                               ├─► plotting/waveforms (5) 可视化验证
                               └─► features (6) ──► filtering (7)
                                    └─► output (8)
                                         ├─► cog (10) ──► track (11)
   cache (9) —— 贯穿，独立
   pipeline (12) 串联全部
   tests/docs (13)
```

**建议实施批次**

1. **批次 A**：模块 1（config/CLI）+ 2（io）+ 3（matching）。
2. **批次 B（新增核心）**：模块 4（clustering）+ 5（可视化验证）+ 6（features，含 dynode 滤波/放大）。
3. **批次 C**：模块 7（筛选）+ 8（output，含 record_id）+ 9（cache，新路径）。
4. **批次 D（重建）**：模块 10（Cog）+ 11（track）。
5. **批次 E（贯通发布）**：模块 12（pipeline/CLI）+ 13（测试/文档）。

---

## 15. 待澄清/待定项（blockers）

- [ ] **COG/径迹**：pmt pattern 数据结构与成熟脚本接口；径迹重建图例与坐标约定。
- [x] **dynode 处理参数**（已确认）：无软件低通（硬件 25 MHz）；`dynode_scale=113`（每通道先 ×113 再 sum）；`area_dyn`/`dynode_area_pe` 基于原始 ×1；1 µs 切片宽度（后续径迹阶段）。
- [x] **筛选阈值**（已固化 2026-09-01）：`n_channels ≥ 7` ∧ `height > 15000` ADC ∧ `anode_sum_area > 10000` PE ∧ `width_ns > 5000` ns（AND）；No-Field 4,682 个 7ch peaks 筛出 **48 候选**。
- [ ] **环境依赖**：`waveform_analysis`、`pmtdata` 安装（`pyth12` 环境）。
- [ ] 聚类与可视化验证的输出规模/文件命名约定。
- [ ] **寻峰算法**：默认实现已落地（借鉴 `findpulse_st_ed`，仅负脉冲、dynode 先翻转）；如用户提供自定义寻峰算法，可替换 `pulse_finder` 实现并调优 `config['pulse_finder']` 阈值（height_threshold/search_range/baseline_samples）。

**已决议事项（2026-08-13）**

- 匹配参数统一：`dynode_shift_ns=6`、窗口 `dt∈[0,40]`，README 已同步更新。
- PMT gain 数据库格式沿用现有读取方式（pmtdata/sqlite/csv），不新增 JSON 后端。
- COG 输出方式：回填至事例 CSV 的 `cog_x`/`cog_y` 列，与 `record_id` 对应。
- run_id 支持外部配置文件（`--run-list`）；CLI 新增 `--plot-peaks`；进度条采用 tqdm；测试覆盖补入 gain/pe_calibration。

**已决议事项（2026-08-14）**

- **peak start/end 重定义**：不再使用"record time min/max"；改为对 peak 内所有 anode+dynode 通道波形分别寻峰，`peak.start = min(各通道 pulse_start)`、`peak.end = max(各通道 pulse_end)`；寻峰算法为可插拔接口（`pulse_finder`），算法本体由用户后续提供，当前为阻塞项（见 §15）。

**已决议事项（2026-08-17）**

- **rise_time 定义**：`peak_index − pulse_start`（start→峰值点）；anode/dynode 两侧均计算（不再用 10%-90% 交叉）。
- **end 判据分侧**：anode 从峰值向右**首次回基线**即 end（`end_consecutive=0`）；dynode 需 end 后连续 3 点保持 ≤20 ADC（稳定确认）。
- **dynode 软件低通取消**：新数据硬件内置 25 MHz 低通电路；算法层 `dynode_lp_cutoff_hz=None` 不滤波，dynode start/end/特征均基于原始波形。
- **dynode 放大 ×113**：`dynode_scale=113`；`dynode_sum` 每通道先 ×113 再对齐求和；`area_dyn`/`dynode_area_pe` 基于原始 ×1。
- **时间参数单位 ns**：`width`/`rise_time`/`width_90area`/`width_50area` 均 ×4ns 计。
- **新 peak 参数**：`width_90area`、`width_50area`（面积占比宽度）、`area_ano`/`area_dyn`（总电荷）。
- **筛选判据已固化（2026-09-01）**：`n_channels ≥ 7` ∧ `height > 15000` ∧ `anode_sum_area > 10000 PE` ∧ `width_ns > 5000 ns`（No-Field 48 候选）；早期 `width_90area > 1000ns 且 rise_time > 80ns` 判据被取代。

**已决议事项（2026-08-31）**

- **peak 级参数统一由 sum 波形计算**：`anode_sum`/`dynode_sum`（pulse_start 对齐逐点求和）为计算基准；命名统一（`peak_height→height`、`peak_width→width`、`peak_rise_time→rise_time`、`peak_width_ns→width_ns`），删除 `*_sum_height/width/rise_time` 等重复字段（保留 `*_sum_area` PE）。
- **面积积分区间**：`[anode_sum start, dynode_sum end]`（sum 寻峰边界）；`area_ano`/`area_dyn` 为原始 ×1 面积，`anode_area_pe`/`dynode_area_pe` 用 **mean-gain** 换算 PE，`anode_sum_area`/`dynode_sum_area` 为 sum 全波形 PE。
