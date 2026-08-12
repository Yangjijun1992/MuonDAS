# Muon 示例筛选与打拿极读出快速分析 分模块实施计划与任务清单

> 配套文档：[muon_dynode_analysis_requirements.md](./muon_dynode_analysis_requirements.md)
>
> 本计划基于需求规格说明书，将系统拆分为多个高内聚、低耦合的模块。每个模块含目标、接口约定、以及可勾选的任务清单。
>
> **基准实现（reference）**：本计划各模块的字段命名、时间匹配、面积/PE 计算与增益数据库访问约定，均以已提供的示例代码为**最终对齐基准**：
> - 数据读取：[`examples/raw_reader.py`](../examples/raw_reader.py)
> - Run 配置（runinfo.json 解析、真实数据路径调取）：[`examples/runinfo.py`](../examples/runinfo.py)
> - 主流程编排： [`examples/pipeline.py`](../examples/pipeline.py)
> - 匹配/筛选/面积/PE/绘图：[`examples/dynode_large_pulse_selection.ipynb`](../examples/dynode_large_pulse_selection.ipynb)
>
> 请结合文末「附录 A：示例代码接口清单」阅读；示例中暂未覆盖的**上升沿/宽度等特征量**作为新增能力纳入开发流程（模块五）。

## 0. 总体架构与目录结构

采用 `src/` + `scripts/` + `config/` + `output/` 的典型 Python 工程布局。

```
MuonDAS/
├── docs/                        # 需求与本文档
├── config/
│   ├── analysis.yaml            # 默认分析参数（筛选阈值、窗口、形状判据）
│   └── data_source.yaml         # 数据目录、文件格式、通道延迟校准、gain 库路径
├── src/muon_analysis/
│   ├── __init__.py
│   ├── config.py                # 配置加载/校验/默认值
│   ├── io/
│   │   ├── __init__.py
│   │   ├── readers.py           # HDF5 / .npy 数据读取抽象
│   │   ├── run_index.py         # run_id 解析（列表/通配符/外部配置文件）
│   │   └── runinfo.py           # runinfo.json 解析、RunInfo、真实数据路径调取
│   ├── matching.py              # 打拿极-阳极时间对齐（含通道延迟校准）
│   ├── filtering.py             # muon 候选事例粗糙筛选
│   ├── features.py              # 特征量计算（charge/height/上升时间/宽度）+ 积分窗口策略
    │   ├── gain.py                  # PMT SPE gain 数据库访问（优先对齐 pmtdata，可扩展 SQLite）
    │   ├── pe_calibration.py        # 积分电荷 -> 光电子数 (PE)：pe_fact/gain
│   ├── plotting/
│   │   ├── __init__.py
│   │   ├── waveforms.py         # 波形可视化（叠加/并排、标注候选区）
│   │   └── distributions.py     # 特征量统计分布图
│   ├── cache.py                 # /tmp/muon_analysis 缓存管理
│   ├── output.py                # CSV / .npy 结果持久化
│   └── pipeline.py              # 主流程编排
├── scripts/
│   ├── run_analysis.py          # 命令行入口
│   └── sample_data.py           # （可选）生成模拟示例数据便于联调
├── tests/                       # pytest 单元测试
└── output/                      # 默认输出目录（CSV/PNG/NPY）
```

**技术决策（依据已提供的示例代码而定）**
- Python 3.10+，主要依赖：NumPy、SciPy、Matplotlib、PyYAML、pandas、h5py。
- 数据读取：**以示例 `waveform_analysis.records_view(ctx, run_id)` 返回的记录为事实标准**（结构化数组字段含 `time/channel/board/record_id/event_length`）；HDF5/`.npy` 作为可选持久化/中间缓存格式，由配置文件选择读取器。
- 通道约定：`board == 1` 为打拿极(dynode)，`board == 0` 为阳极(anode)。
- gain 数据库：**优先复刻示例的 `pmtdata.PMTDataClient.get_pmt_data()`**（run_id/channel_id/gain），并封装统一抽象接口，可再扩展 SQLite/CSV 后端（原始选择 SQLite 优先，改为以 pmtdata 为基准、SQLite 作为可选替换）。
- 性能：NumPy 向量化 + 可选 `multiprocessing`/`concurrent.futures` 并行按 run 处理。

---

## 1. 模块一：配置与命令行接口（config / CLI）

**目标**：集中管理所有可调参数；提供清晰、可复用的命令行接口。

**接口约定**
- 配置为 YAML，分 `analysis`（阈值/窗口/形状）与 `data_source`（格式/延迟/gain 路径）两组，支持 CLI 覆盖关键项。
- CLI 参数（argparse）：`run_id`（N 个，支持通配符）、`--config`、`--out-dir`、`--save-waveforms/--no-save-waveforms`、`--plot-ids`、`--clear-cache`、`--show-cache`、`--debug`、`--parallel`。

**任务清单**
- [ ] 定义 config 数据模型与默认值（阈值、时间窗、匹配窗口、形状判据、积分窗口策略、目录、gain 库路径）。
- [ ] 将示例默认参数纳入 `analysis.yaml`：`match_window_ns=[0,30]`、`dynode_shift_ns=16`、`sample_interval_ns=4`、`asym_min=0.7`、`min_event_length=7000`、`min_seg_area_pe=20000`、`integral_window_mode=fixed`（`integral_start=20`、`integral_end=100/60`；预留 `peak_finder` 模式，后期接入寻峰算法）、并含 `dynode_scale=110`、`plot_len=100`、`cutoff_hz=20e6`、`fs=250e6` 等绘图默认值）。
- [ ] 实现 YAML 加载、参数覆盖（CLI > 用户配置文件 > 默认值）与校验。
- [ ] 实现 `scripts/run_analysis.py` argparse 参数解析与帮助文本。
- [ ] 配置版本号：`parameter_version`，用于结果可重复性标注。
- [ ] （联调）提供默认示例 `config/*.yaml`（data_source 含数据目录、gain/pmtdata 配置、`pyth12`/`waveform_analysis` 环境依赖说明）。

---

## 2. 模块二：数据读取（io）

**目标**：批量解析多 run（每 run 依 runinfo 调取配置与真实数据路径）的打拿极(dynode)与阳极(anode)数据，容错跳过坏 run。

**接口约定**
- `get_runinfo(run_id, data_root="/mnt/data/TPC") -> RunInfo`：调取每个 run 的配置与真实数据路径（**对齐示例 `runinfo.py`**）。
- `read_run(runinfo, cfg) -> RunData`：`RunData` 含时间戳、波形数组（dynode/anode）、通道号与元信息。
- `resolve_run_ids(list|glob|config_file) -> list[str]`。
- 读取器**对齐示例 `raw_reader.py` 的 `RawDataBundle` / `NotebookBasedRawDataReader`**：基于 `waveform_analysis` 的 `records_view(ctx, run_id)` 返回结构化 records；HDF5/`.npy` 作为可选持久化/中间格式读取器，按配置选择。
- 分离打拿极/阳极：`records[records["board"] == 1]` → dynode，`== 0` → anode。

**RunInfo 调取流程（对齐 `runinfo.py`）**
- `normalize_run_id`（补零到 5 位）→ `discover_runinfo_path`（`run_R8520/<rid>/runinfo.json`）→ `load_runinfo_json` → `build_runinfo`。
- 从 `runinfo.json` 获取 `datatype`（dark rate / spe gain / after pulse）、`raw_dir`（outfile_path 或回退 `run_dir/RAW`）、`mapping`（board_id/channel→pmt_id）、及全部元信息。

**任务清单**
- [ ] 移植/封装 `runinfo.py`：`RunInfo`、`normalize_run_id`、`discover_runinfo_path`、`load_runinfo_json`、`build_runinfo`、`get_runinfo`。
- [ ] 解析 runinfo 的 `datatype` 与 `mapping`（board_id/ch → pmt_id）用于辅助匹配/读出。
- [ ] 移植/封装 `raw_reader.py`：`resolve_raw_input_path`、`load_raw_data_from_notebook_logic`、`summarize_raw_data`、`RawDataBundle`。
- [ ] 实现 `run_id` 解析（列表、通配符 glob、外部配置文件）。
- [ ] 实现按 `board` 分离 dynode/anode records。
- [ ] 实现 `.npy` / HDF5 可选读取器（时间戳、波形、元信息）。
- [ ] 定义统一 `RunData` 数据结构（dataclass）。
- [ ] 文件缺失/格式错误/waveform_analysis 不可用/runinfo 缺失 → 打印明确 WARNING 并 `skip` 当前 run，不中断批次。
- [ ] 单元测试：构造最小 runinfo.json 与示例文件验证解析与容错。

---

## 3. 模块三：时间匹配（matching）

**目标**：打拿极与阳极信号高精度时间对齐，输出配对事件列表。

**对齐示例逻辑（`dynode_large_pulse_selection.ipynb`）**
- 先对打拿极时间戳整体迁移 `+16 ns`（`shift_time_records`，4 sample × 4ns）。
- 用 pandas `merge_asof` 按 `channel` 物理隔离匹配，`direction='backward'`。
- 计算 `dt = t_dyn - t_ano`，筛选窗口 `min_diff ≤ dt ≤ max_diff`（示例默认 `[0, 30] ns`）。
- 输出 `dynode_idx` / `anode_idx` / `dt` / `channel`。

**接口约定**
- `match_events(run_data, cfg) -> DataFrame`：列 `[dynode_idx, anode_idx, dt, channel]`。
- 时间匹配窗口与 dynode 时间迁移量放入配置文件（`match_window_ns=[0,30]`、`dynode_shift_ns=16`、`sample_interval_ns=4`）。
- 通道延迟校准参数从 `data_source` 配置读取（对齐 `shift_time_records` / 按通道 `channel_delay`）。

**任务清单**
- [ ] 移植 `shift_time_records`（dynode 时间迁移，改由配置驱动）。
- [ ] 移植 `get_matched_indices_by_channel`（`merge_asof` + `dt` 窗口筛选）。
- [ ] 匹配窗口/迁移量/采样间隔参数集中到配置文件。
- [ ] 输出 `MatchedEvent`（dynode_idx/anode_idx/dt/channel）。
- [ ] （可选）中间匹配结果可缓存（见模块八）。
- [ ] 单元测试：构造已知时间偏移的数据验证对齐正确性。

---

## 4. 模块四：muon 候选事例粗糙筛选（filtering）

**目标**：基于幅度阈值、时间符合窗口、脉冲形状等条件筛选候选事例。

**对齐示例的筛选逻辑（可配置化）**
- **噪声剔除**：`asymmetry_calculation`（正/负脉冲）→ 保留 `asym > 0.7`（示例）。
- **大脉冲挑选**：`event_length > 7000` 且 `seg_area_pe > 20000`（示例大脉冲事例）。
- 匹配/时间符合筛选已在模块三完成。

**接口约定**
- `filter_candidates(matched_records, cfg) -> list[Candidate]`；`Candidate` 含候选标识及基本属性（幅度、时间、asym、面积、通过项）。
- 所有判据参数（`asym_min`、`min_event_length`、`min_seg_area_pe`、幅度阈值等）均来自 `config/analysis.yaml`。

**任务清单**
- [ ] 移植 `asymmetry_calculation`（批量处理、正/负极性、baseline/peak/valley）。
- [ ] 实现基于 `asym > asym_min` 的噪声剔除（dynode 正、anode 负）。
- [ ] 移植/实现面积筛选（`seg_area_pe`、`event_length` 阈值）。
- [ ] 实现幅度阈值（height ≥/≤，dynode 与 anode 可分别设定）。
- [ ] 时间符合窗口（模块三已部分覆盖，此处汇总为筛选条件）。
- [ ] 脉冲形状判据（脉宽、上升时间范围，基于模块五特征量或简化判据）。
- [ ] 参数全部集中到配置文件。
- [ ] 输出候选事例集合及基本属性。
- [ ] 单元测试：构造正/负例验证筛选正确性。

---

## 5. 模块五：特征量与 PE 标定（features / gain / pe_calibration）

**目标**：计算特征量，并按通道查询 PMT SPE gain，积分电荷换算为光电子数。

**面积（charge）积分策略（重要说明）**
- **初版**：采用**固定窗口/给定区间**积分（对齐示例 `compute_integral_pe`，如 `[start,end)`，用于 `area_pe`）。
- **更合理的目标方案（后期补齐）**：由**寻峰算法**自动定位波形起始点，再从起始点积分；用户后期可提供寻峰算法（确定波形起始位置）挂接替换。
- 因此模块预留**积分策略接口**，将「积分区间求取」抽象为可插拔组件：默认实现 = 固定窗口；后续接入寻峰起点策略而不改动调用方。

**积分区间求取接口（预留）**
- `IntegrationWindowResolver`（抽象基类）→ `resolve(waveform, baseline, ...) -> (start, end)`。
  - `FixedWindowResolver(start, end)`：初版默认实现。
  - `PeakFinderWindowResolver`：占位/预留，后续由用户提供寻峰算法实现（确定波形起始位置后积分）。
- 上下采样窗口长度不足时自动截断（对齐示例 `actual_end = min(integral_end, n_samples)`）。

**接口约定**
- `compute_charge(waveform, window_resolver, signal_polarity) -> charge`：按窗口求积分电荷。
- `compute_features(waveform_segment) -> Features{charge, height, rise_time, width, ...}`。
- gain 数据库抽象 `GainDB`（首版实现 `SQLiteGainDB`），`get_gain(channel_id) -> float`（及增益版本 `gain_db_version`）。
- `charge_to_pe(charge, gain) -> float`。

**任务清单**
- [ ] 设计可插拔的积分区间接口 `IntegrationWindowResolver`（含默认 `FixedWindowResolver` 与预留的寻峰策略）。
- [ ] 实现基于窗口解析器的面积计算 `compute_charge`（固定窗口 [start,end)，正/负极性，窗口越界自动截断）。
- [ ] `FixedWindowResolver`：初版默认固定/给定区间（示例 [20,100] 或 [20,60]，可配置）。
- [ ] 预留 `PeakFinderWindowResolver` 抽象与占位实现（TODO：待用户提供寻峰算法后确定波形起始点）。
- [ ] 实现特征量计算（积分面积、峰高、上升时间 10%-90%、半高宽/宽度）。
- [ ] 拟合 `pe_fact = (2./16384) * 4.e-9 / (50 * 1.6e-19) / 1.e6`；`pe_calib = pe_fact / gain`。
- [ ] 设计 gain 数据库抽象接口；**优先移植示例 `pmtdata.PMTDataClient.get_pmt_data()`**（run_id/channel_id/gain），同时提供 SQLite/CSV 可选后端。
- [ ] 支持按 `run_id` + `channel_id` 查询 gain，`gain==0` 时报错/跳过。
- [ ] 移植 `compute_integral_pe`（基于窗口解析器，`area_pe`）。
- [ ] 移植 `compute_raw_segment`（整段积分，`seg_area_pe`）。
- [ ] （新增，示例未含）实现**上升时间、半高宽/宽度、峰高(height)** 特征量，纳入开发流程。
- [ ] 记录 gain 库标识（`gain_db_version`）到输出。
- [ ] 单元测试：用已知高斯脉冲验证特征量；用已知 gain 验证 PE 换算；验证固定窗口与窗口越界截断。

---

## 6. 模块六：波形可视化与验证（plotting/waveforms）

**目标**：叠加/并排绘制 dynode 与 anode 波形，高亮候选区，支持交互缩放与保存 PNG。

**对齐示例的绘图函数**
- `plot_pmt_comparison`（打拿极放大 `dynode_scale` 叠加到阳极坐标系）。
- `plot_by_record_id` / `plot_dyn_by_record_id` / `plot_dyn_multiband_by_record_id`（按 record_id 对 dynode/anode 按时间对齐绘制）。
- 低通滤波 `apply_lowpass_filter`（`scipy.signal.butter` + `filtfilt`，20 MHz @ 250 MHz，零相位，用于检查/验证）。
- 示例默认参数：`sample_interval_ns=4`、`dynode_scale=110`、`plot_len=100`、`cutoff_hz=20e6`、`fs=250e6`。

**接口约定**
- `plot_waveform(event, out_path, mode='overlay'|'sidebyside')`；`plot_by_record_id(record_id,...)`。
- 交互式：Matplotlib 默认缩放/平移；`--plot-ids` 指定事例，否则自动批量。

**任务清单**
- [ ] 移植 `apply_lowpass_filter`（低通滤波器）。
- [ ] 移植 `plot_pmt_comparison`（叠加对比，dynode 放大/反相、按 channel 筛选）。
- [ ] 移植 `plot_by_record_id`（按 record_id 时间对齐绘制 dynode/anode）。
- [ ] 候选脉冲区域高亮标注（基于匹配/筛选时间窗）。
- [ ] 保存为 `.png`（自动批量 or 指定事例序号）。
- [ ] 交互式缩放/平移验证（依赖 Matplotlib 后端）。
- [ ] 样例输出目测验证。

---

## 7. 模块七：特征量统计分布图（plotting/distributions）

**目标**：生成 PE 谱、时间差谱、面积-长度相关图等统计分布，验证筛选条件合理性，保存 PNG。

**对齐示例的绘图**
- `plot_correlation`（Anode Area vs Dynode Area 二维散点，按 channel 分色）。
- `plt.hist2d(seg_area_pe, event_length)`（面积对波形长度），`plt.hist` 分布图。

**接口约定**
- `plot_distributions(candidates_df, out_dir)` 输出多张 PNG（PE 谱、dynode-anode 时间差谱、anode-dynode 面积相关、seg_area_pe vs event_length、height/charge 分布等）。

**任务清单**
- [ ] 移植 `plot_correlation`（anode/dynode area 相关散点，按通道分色）。
- [ ] 实现 `seg_area_pe` vs `event_length` 二维直方图。
- [ ] 实现 PE 谱直方图。
- [ ] 实现 dynode-anode 时间差谱。
- [ ] 实现 height/charge/rise_time 等分布图。
- [ ] 图像保存 `.png` 至指定目录。

---

## 8. 模块八：缓存管理与数据溯源（cache）

**目标**：中间数据缓存至 `/tmp/muon_analysis/`，以 `run_id + 参数哈希` 命名，保证一致性与避免重复计算。

**接口约定**
- `cache_path(run_id, param_hash) -> /tmp/muon_analysis/<run_id>_<hash>.<ext>`。
- `param_hash = sha1(cfg_param_bytes + gain_db_version)`。
- CLI：`--clear-cache` 清空该目录；`--show-cache` 列出条目及对应原始数据标识。

**任务清单**
- [ ] 实现 key 哈希（run_id + 处理参数 + gain 版本）。
- [ ] 实现缓存读写（匹配后事件结构等中间数据）。
- [ ] 实现 `--show-cache`：列出条目与溯源标识。
- [ ] 实现 `--clear-cache`：清空 `/tmp/muon_analysis/`。
- [ ] 缓存空间不足警告（不自动清除）。
- [ ] 单元测试：哈希一致性 + (无缓存/命中缓存) 行为。

---

## 9. 模块九：结果输出（output）

**目标**：保存波形片段 `.npy`、事例级参数 CSV、统计图 PNG。

**接口约定**
- `save_waveforms_npy(candidates, out_dir)`（可由参数关闭）。
- `save_events_csv(candidates_df, out_dir)`：run_id、event_id、PE、height、time 等 + `parameter_version` 与 `gain_db_version` 溯源列。
- CSV 用 pandas 写出。

**任务清单**
- [ ] 事例级 CSV 输出（含溯源列：parameter_version、gain_db_version）。
- [ ] 波形片段 `.npy` 保存（`--save-waveforms/--no-save-waveforms`）。
- [ ] 统计分布图 PNG 输出。
- [ ] 输出目录自动创建；全部文件按指定目录落盘。

---

## 10. 模块十：主流程编排与多进程（pipeline + CLI）

**目标**：串联 runinfo→读取→匹配→筛选→特征→绘图→输出；进度条/关键统计；可选多进程并行。

**对齐示例 `pipeline.py` 的编排模式**
- **顶层入口**：`analyze_runs(run_ids, output_dir, data_root, ...)`，逐 run 循环。
- 每 run：`get_runinfo` → `reader.read`（打印 run_id/type/datatype/raw_dir/event_count/channel_count 等）→ 按 `datatype` 分支分析 → 生成图 → 写库。
- **容错**：外层对每个 run 包 `try/except`，异常打印 `[run_id=...] ERROR` 后继续下一个，不中断批次；最后打印汇总（处理 run 数/产物路径）。
- 结果对象：dataclass（如 `DarkCountResult`/`GainAnalysisResult`），携带行列级数据供统计与绘图复用。

**接口约定**
- `analyze_runs(run_ids, output_dir, data_root=DEFAULT_TPC_DATA_ROOT, ...) -> int`（对齐示例签名）。
- `RunReport`：含每 run 总事件数、通过筛选数、产物路径。
- 并行：按 run 粒度的 `ProcessPoolExecutor`（`--parallel`）。

**任务清单**
- [ ] 移植/对齐 `analyze_runs` 编排骨架与打印/汇总风格（`[run_id=...]` 日志、最终 Summary）。
- [ ] 主流程：runinfo → 读取 → 匹配 → 筛选 → 特征/PE → 绘图 → 输出（含缓存命中短路）。
- [ ] 进度条/关键统计输出（tqdm 或自绘；总事件数、通过筛选数）。
- [ ] 按 run `try/except` 容错，失败 run 不中断批次并汇总报告。
- [ ] 多进程并行（可选，`--parallel`）。
- [ ] `scripts/run_analysis.py` 完整接线。

---

## 11. 模块十一：测试与文档

**目标**：可维护性/可重复性验证。

**任务清单**
- [ ] pytest 覆盖 io/matching/filtering/features/gain/pe/cache/output。
- [ ] 提供运行说明（README 或 usage）与配置文件注释。
- [ ] 示例数据生成脚本 `scripts/sample_data.py`（便于无真实数据时联调）。

---

## 12. 依赖关系与建议实施顺序

依赖顺序（拓扑排序）：

```
config/CLI (1)
  └─ io (2)
       └─ matching (3)
            └─ filtering (4)
                 ├─ features (5a) + gain/pe (5b)
                 └─ plotting/waveforms (6)
                 └─ plotting/distributions (7)
                 └─ cache (8) —— 贯穿，独立
                 └─ output (9)
                      └─ pipeline (10) 串联全部
                           └─ tests/docs (11)
```

**建议实施批次**（基于已提供的示例代码，可直接对齐开发）
1. **批次 A（骨架 + 数据接入）**：模块 1（配置/CLI）+ 模块 2（io，移植 `raw_reader.py`）+ `sample_data.py`。
2. **批次 B（核心逻辑，深度对齐 ipynb）**：模块 3（matching：`merge_asof` 匹配）+ 模块 4（filtering：asym/长度/面积筛选）+ 模块 5（features/gain/pe：面积积分、`pe_fact/gain`、新增上升沿/宽度）。
3. **批次 C（输出与缓存）**：模块 6/7（绘图：`plot_pmt_comparison`/`plot_by_record_id`/`plot_correlation`）+ 模块 8（cache）+ 模块 9（output）。
4. **批次 D（贯通发布）**：模块 10（pipeline/并行/CLI 接线）+ 模块 11（测试/文档）。

> **基准统一**：模块 2/3/4/5/6/7 的字段命名、匹配/筛选/面积/PE 计算与绘图逻辑，一律以 `examples/` 下的 `raw_reader.py` 与 `dynode_large_pulse_selection.ipynb` 为最终对齐基准（见附录 A）。**新增**的上升沿/宽度等特征量不属于示例，将作为扩展能力开发并单测。

## 13. 待澄清/待定项（blockers）

- [x] **example 脚本**：已提供 —— `examples/raw_reader.py` + `examples/dynode_large_pulse_selection.ipynb` + `examples/runinfo.py` + `examples/pipeline.py`。
- [ ] **示例数据**：用于联调的真实或近真实数据文件路径（或可用数据文件的具体位置）。
- [ ] **环境依赖**：`waveform_analysis`、`pmtdata` 包的安装来源/版本（`raw_reader.py` 注明需 `pyth12` 环境）；是否有配套数据库文件。
- [ ] 各筛选阈值的**默认数值**（asym 阈值默认 0.7、min_event_length=7000、min_seg_area_pe=20000 等来自示例，其余先占位，后续依据物理预期标定）。
- [ ] PE 谱/bin、绘图风格等默认参数细节（dynode_scale=110、plot_len=100 等示例默认值先复用）。

---

## 附录 A：示例代码接口清单（对齐基准）

### A.1 Run 配置调取 —— `examples/runinfo.py`
| 接口 | 说明 |
|---|---|
| `RunInfo`(dataclass，来自 `pmt_analysis.models`) | `run_id/runtype/run_dir/runinfo_path/raw_dir/outfile_name/source/datatype/metadata` |
| `normalize_run_id(run_id)` | 补零到 5 位（`zfill(5)`） |
| `discover_runinfo_path(run_id, data_root="/mnt/data/TPC")` | `run_R8520/<rid>/runinfo.json` |
| `load_runinfo_json(path)` | 解析 runinfo.json |
| `build_runinfo(run_id, runinfo_path, payload)` | 组装 `RunInfo`：`raw_dir` 取 `outfile_path` 或回退 `run_dir/RAW`；解析 `datatype`、`run_tag`、全部元信息 |
| `get_runinfo(run_id, data_root)` | 一站式：discover + load + build |

- `datatype`（来自 `run_comment`）：`dark rate` / `spe gain` / `after pulse`；无效则抛 `RunInfoValidationError`。
- `validate_run_tag`：要求 `run_tag == "pmt test"`。
- 每 run 的**真实数据路径**统一经 `RunInfo.raw_dir` 获取（供 `raw_reader` 使用）。

### A.2 数据读取 —— `examples/raw_reader.py`
| 接口 | 说明 |
|---|---|
| `RawDataBundle`(dataclass) | 统一原始数据容器：`runinfo/source_path/data/data_format/event_count/channel_count/waveform_count/metadata` |
| `resolve_raw_input_path(runinfo)` | 由 `runinfo.raw_dir` 用 `glob("*_raw_*.bin")` 解析二进制文件 |
| `load_raw_data_from_notebook_logic(input_paths, runinfo)` | 用 `waveform_analysis`：`Context(storage_dir=...)` + `records_view(ctx, run_id)`，返回 records view |
| `summarize_raw_data(data)` | 汇总 event/channel/waveform/board/时间范围/波形长度等 |
| `NotebookBasedRawDataReader.read(runinfo)` | 组装 `RawDataBundle` |

records 字段：`time`(ns)、`channel`、`board`、`record_id`、`event_length`、`channel_count` 等。`board==1` dynode、`board==0` anode。

### A.3 主流程编排 —— `examples/pipeline.py`
- 顶层入口：`analyze_runs(run_ids, output_dir, data_root=DEFAULT_TPC_DATA_ROOT, save_plots, write_db, fit_model, noise_suppression_enabled, ...) -> int`。
- 逐 run：`get_runinfo → reader.read(bundle) → 按 datatype 分支分析 → 绘图 → 写库`，每步打印 `[run_id=...]` 日志。
- **容错模式**：每个 run 外层 `try/except`，异常不中断批次；runinfo 无效则跳过；结束打印汇总（`Runs processed: X/Y`、产物路径列表）。
- 结果对象为 dataclass（`DarkCountResult`/`GainAnalysisResult`/`AfterpulseResult`），容纳总量与逐通道结果。
- `pmt_id_map`：由 runinfo 的 `mapping`（`board_id`→channels→`pmt`）构造 `(board_id, ch) -> pmt_id`。

### A.4 时间匹配 —— ipynb（cell 9 / 14）
- `shift_time_records(records)`：dynode 时间 `+= 16 ns`（4 sample × 4ns，配置化）。
- `get_matched_indices_by_channel(raw_rec_ano, raw_rec_dyn, min_diff=0, max_diff=30)`：
  - pandas `merge_asof`，`on='time'`、`by='channel'`、`direction='backward'`；
  - `dt = t_dyn - t_ano`，筛选 `min_diff ≤ dt ≤ max_diff`；
  - 返回 `[dynode_idx, anode_idx, dt, channel]`。

### A.5 噪声/面积/PE —— ipynb（cell 25 / 42 / 45 / 41）
- `asymmetry_calculation(records, rv, signal_polarity)`：`asym = (peak-baseline)/range`（正）或 `(baseline-valley)/range`（负），`baseline_samples=10`。
- `get_pmt_gain_map(run_id)`：`pmtdata.PMTDataClient().get_pmt_data()` → `{channel_id: gain}`。
- `pe_calibration(pmt_id, run_id)`：`pe_fact/gain`，`pe_fact = (2./16384)*4.e-9/(50*1.6e-19)/1.e6`。
- `compute_integral_pe(..., integral_start=20, integral_end=100, area_field='area_pe')`：窗口积分 → PE。
- `compute_raw_segment(..., area_field='seg_area_pe')`：整段积分 → PE。
- 含义：`area_pe` 为匹配窗口内固定区间积分；`seg_area_pe` 为整段波形面积。

### A.6 筛选/挑选 —— ipynb（cell 30 / 54）
- 噪声剔除：`asym > 0.7`（示例阈值，dynode 正 / anode 负）。
- 大脉冲：`event_length > 7000` 且 `seg_area_pe > 20000`。
- 再按匹配 `anode_idx`/`dynode_idx` 取出对应波形对。

### A.7 绘图 —— ipynb（cell 22 / 36 / 49 / 52）
- `apply_lowpass_filter(waveform, cutoff_hz=20e6, fs=250e6, order=4)`：`butter` + `filtfilt`，零相位。
- `plot_pmt_comparison(raw_ano, raw_dyn, rv, num_samples, channel_id, plot_length=100, dynode_scale=110, invert_dynode, dt=16)`：叠加对比，dynode `-sig*dynode_scale`。
- `plot_by_record_id(raw_ano, raw_dyn, rv, record_id, plot_len, sample_interval_ns=4.0, ...)`：按时间对齐绘制单对。
- `plot_dyn_by_record_id` / `plot_dyn_multiband_by_record_id`：dynode 单/多 band 绘制。
- `plot_correlation(raw_ano, raw_dyn)`：Anode Area vs Dynode Area 散点（按 channel 分色）。
- `plt.hist2d(seg_area_pe, event_length)`：面积对长度二维直方图。

### A.8 示例默认参数速查
`data_root="/mnt/data/TPC"`、`runtype="run_R8520"`、`runinfo.json` 路径、`sample_interval_ns=4`、`shift=16ns`、`match_window=[0,30]ns`、`asym_min=0.7`、`min_event_length=7000`、`min_seg_area_pe=20000`、`integral_start=20`、`integral_end=100`（匹配窗口面积）/ `60`（大脉冲）、`dynode_scale=110`、`plot_len=100`、`cutoff_hz=20e6`、`fs=250e6`。
