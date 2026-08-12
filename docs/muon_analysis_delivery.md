# Muon 分析工具 - 交付内容

> 本文档记录当前已完成的交付内容，用于后续排查开发流程的完善情况。
> 配套文档：[需求规格](muon_dynode_analysis_requirements.md)、[实施计划与任务清单](muon_dynode_analysis_implementation_plan.md)。

**状态**：全部完成（40 项 pytest 通过，pyflakes 无告警，CLI 顺序/并行端到端可运行）。

---

## 项目结构

```
MuonDAS/
├── config/                            # YAML 参数配置
│   ├── analysis.yaml                  # 全部可调参数（阈值/窗口/积分策略/gain/输出）
│   └── data_source.yaml               # 数据根目录/runtype
├── src/muon_analysis/                 # 核心包（模块化）
│   ├── config.py                      # 配置加载/校验/默认值/参数哈希
│   ├── models.py                      # RunInfo、核心数据模型
│   ├── matching.py                    # 打拿极-阳极时间匹配
│   ├── filtering.py                   # 候选事例粗糙筛选
│   ├── features.py                    # 特征量 + 积分窗口策略接口
│   ├── gain.py                        # PMT SPE gain 数据库
│   ├── pe_calibration.py              # 电荷 -> PE 换算
│   ├── cache.py                       # /tmp 缓存管理
│   ├── output.py                      # CSV/NPY 结果持久化
│   ├── pipeline.py                    # 主流程编排 + 多进程
│   └── io/
│   │   ├── runinfo.py                 # runinfo.json 解析/真实路径调取
│   │   ├── readers.py                 # waveform_analysis 后端读取
│   │   ├── readers_alt.py             # npy / hdf5 后端读取
│   │   ├── run_index.py               # run_id 解析
│   │   └── data.py                    # RunData（按 board 分离）
│   └── plotting/
│       ├── waveforms.py               # 波形可视化（低通/叠加/时间对齐）
│       └── distributions.py           # 统计分布图
├── scripts/
│   ├── run_analysis.py                # 命令行入口
│   └── sample_data.py                 # 离线示例数据生成
├── tests/                             # pytest 单元测试（40 项）
├── docs/                              # 需求 / 计划 / 本文档
├── examples/                          # 参考实现（raw_reader/runinfo/pipeline/ipynb）
└── README.md
```

## 模块清单与功能

### 模块1 - 配置与命令行（config / CLI）
- `config.py`：加载 `analysis.yaml`，覆盖优先级 **CLI > 用户配置 > 默认值**；配置校验（积分窗口模式、gain 后端）；`param_hash` 参数哈希（排除输出/缓存等易变字段）。
- `config/analysis.yaml`：全部可调参数集中管理（匹配窗口、筛选阈值、积分窗口策略、gain 路径、输出、绘图默认值等）。
- `scripts/run_analysis.py`：argparse，支持多 run_id、`--config/--data-root/--data-format/--runtype/--runtype-candidates/--out-dir/--plot-ids/--parallel/--gain-backend/--gain-path/--relaxed-filters/--show-cache/--clear-cache` 等。

### 模块2 - 数据读取（io）
- `runinfo.py`：`get_runinfo(run_id, data_root, runtype, runtype_candidates)` 调取每 run 配置与真实数据路径。
  - **runtype 作用域**：run_id 可能位于不同 runtype 目录（`run_R8520` / `run5_Ar` / `run6_Xe` / `run7_Xe` 等）。支持显式 `runtype` 限定搜索路径；未指定时**自动探测**（`discover_runtype` 扫描 `data_root` 下的 runtype 目录）。
  - `run_info.runtype`（runinfo.json 内）为权威 runtype。
  - **宽松校验**：默认非严格模式，`run_tag`/`datatype` 不匹配（如 TPC/muon 运行）时降级为空 datatype 并警告，不阻断加载。
- `readers.py`：`waveform_analysis` 后端（需 `pyth12` 环境），按 `board==1`/`0` 分离 dynode/anode。
- `readers_alt.py`：`npy` / `hdf5` 可选后端（离线/中间持久化）。
- `run_index.py`：run_id 列表、通配符（glob）、外部配置文件解析。
- `data.py`：`RunData` 容器 + `split_by_board`。
- 容错：文件/runinfo 缺失等打印 WARNING 并跳过当前 run，不中断批次。

### 模块3 - 时间匹配（matching）
- `shift_time_records`：dynode 时间 +16ns（默认，配置化）。
- `get_matched_indices_by_channel`：pandas `merge_asof` 按 channel 匹配（`direction='backward'`）。
- `dt = t_dyn - t_ano`，筛选窗口 `[min_diff, max_diff]`（默认 `[0,30]ns`）。
- 支持按通道延迟校准（`channel_delay_ns`）。

### 模块4 - 候选事例粗糙筛选（filtering）
- `asymmetry_calculation`：正/负脉冲波形不对称度噪声剔除（默认 `asym>0.7`）。
- 波形长度筛选（默认 `event_length >= 7000`）、段面积筛选（默认 `seg_area_pe >= 20000`）。
- 可选高度（幅度）阈值（dynode/anode 分别设定）。
- 所有参数集中配置文件。

### 模块5 - 特征量与 PE 标定（features / gain / pe_calibration）
- **积分窗口策略接口** `IntegrationWindowResolver`：
  - `FixedWindowResolver`（默认固定/给定区间 `[start,end)`，越界自动截断）。
  - `PeakFinderWindowResolver`：**预留寻峰算法接入点**（待用户提供，定位波形起始点后积分）。
  - 通过 `features.integral_window_mode`（`fixed` / `peak_finder`）切换。
- `compute_features`：峰高(height)、电荷(charge)、上升时间、半高宽(width)、基线。
- `gain.py`：抽象 `GainDB`，后端 `pmtdata`（对齐示例）/ `sqlite` / `csv`，返回 `version` 供溯源。
  - `pmtdata` 后端按 `spe_gain` 列读取；gain 按**当前分析 run 的 run_id** 查询；该 run 无增益记录时**回退到每通道最新测量值**。
  - `build_gain_db(config, run_id=...)` 支持按 run 覆盖增益 run_id。
- `pe_calibration.py`：`pe_fact = (2/16384)*4e-9/(50*1.6e-19)/1e6`，`pe_calib = pe_fact/gain`；`compute_integral_pe` / `compute_raw_segment_pe`。

### 模块6/7 - 可视化（plotting）
- `waveforms.py`：`apply_lowpass_filter`（Butterworth 20MHz@250MHz 零相位）、`plot_pmt_comparison`（叠加对比、dynode 放大/反相）、`plot_by_record_id`（按时间对齐绘制单对）。
- `distributions.py`：`plot_correlation`（anode vs dynode area 按通道分色）、`seg_area_pe` vs `event_length` 2D 直方、PE 谱、时间差谱等，输出 `.png`。

### 模块8 - 缓存管理与数据溯源（cache）
- 缓存目录 `/tmp/muon_analysis/`，键为 `run_id` + `param_hash`。
- `read_npy/write_npy`、`show_cache`、`clear_cache`。
- 空间不足警告（不自动清除）。

### 模块9 - 结果输出（output）
- 事例级 CSV：`run_id / event_id / PE / height / time / parameter_version / gain_db_version` 等。
- 波形片段 `.npy`（`.npz`，参数控制开/关）。
- 统计分布图 `.png`；运行元数据 JSON。
- **每 run 输出目录**：`<输出基目录><run_id>`（如 `--out-dir /tmp/mm_out` → `/tmp/mm_out00183`），便于按完整 run 号识别。

### 模块10 - 主流程编排与多进程（pipeline + CLI）
- `analyze_runs`：逐 run 执行 runinfo → 读取 → 匹配 → 筛选 → 特征/PE → 绘图 → 输出。
- 按 run `try/except` 容错，失败不中断批次；汇总报告。
- 多进程 `ProcessPoolExecutor`（`--parallel`），异常回退顺序执行。
- 匹配结果缓存命中短路（跨配置参数哈希隔离）。

### 模块11 - 测试与文档
- `tests/`：50 项 pytest，覆盖 config/runinfo/matching/features/gain/pe/filtering/cache/output/plotting/readers/pipeline（含缓存复用、并行、`_sig` 波形长度补零、runtype 探测）。
- `README.md`：安装/用法/离线示例。
- pyflakes 无告警。

## 真实数据验证（run 00183）

- run_id `00183` 位于 `runtype = run6_Xe`：`/mnt/data/TPC/run6_Xe/00183/`（内容含 `runinfo.json`、`RAW/*_raw_*.bin`）。
- 自动探测 runtype 成功（未指定 runtype 时定位到 `run6_Xe`）；run `run_tag`/`datatype` 为自由文本（`TPC Run`），宽松校验降级为空 datatype 并继续。
- 读取 **50,125,298** 条波形记录（约 82GB 内存）→ 时间匹配 **960,196** 对（`dt∈[0,30]ns`）→ 默认阈值筛选出 **11** 个 muon 候选。
- 产物：`events_run_00183.csv`（含 `anode/dynode_seg_area_pe`、`event_length`、`parameter_version` 等溯源列，PE 已按通道增益换算）。
- 通道：board0 阳极(negative)/board1 打拿极(positive)，channels 9–15；`pmtdata` 无 00183 的增益条目，回退到每通道最新 `spe_gain`。
- 阈值默认值（`min_seg_area_pe=20000`、`event_length>=7000`）偏严，仅 11 例通过；可经 `config/analysis.yaml` 调整。

## 已知限制 / 待完善（排查项）

- [ ] 真实 `waveform_analysis` / `pmtdata` 后端需 `pyth12` 环境；离线以 `npy` + `sqlite` 后端验证。
- [ ] **寻峰算法接口已预留**（`PeakFinderWindowResolver`），待用户提供寻峰算法以确定波形起始点后接入（替换固定窗口）。
- [ ] 各筛选阈值默认值为示例参考值（`asym>0.7`、`len>=7000`、`area>=20000`），对 run 00183 偏严，需按真实物理预期标定。
- [ ] 极性目前按惯例假定 anode=negative、dynode=positive；可后续从 runinfo `mapping.polarity` 读取以适配各 run。
- [ ] 并行按 run 粒度实现，尚未做进程内波形级并行；单 run 全量读取内存占用高（约 82GB）。

## 快速自检命令

```bash
# 单元测试
python -m pytest tests/

# 静态检查
python -m pyflakes src/ scripts/ tests/

# 离线端到端（示例数据）
python scripts/sample_data.py --run-id 00179 --out /tmp/muon_demo
python scripts/run_analysis.py 00179 \
    --data-root /tmp/muon_demo --data-format npy --relaxed-filters \
    --gain-backend sqlite --gain-path <你的增益库>.db

# 真实数据（自动探测 runtype，pmtdata 增益）
python scripts/run_analysis.py 00183 \
    --gain-backend pmtdata \
    --out-dir /tmp/mm_out          # 输出到 /tmp/mm_out00183/

# 显式指定 runtype（限定搜索路径）
python scripts/run_analysis.py 00183 --runtype run6_Xe --out-dir /tmp/mm_out

# 缓存管理
python scripts/run_analysis.py --show-cache
python scripts/run_analysis.py --clear-cache
```
