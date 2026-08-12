# Muon 事例筛选与打拿极读出快速分析

基于 `docs/muon_dynode_analysis_requirements.md` 的快速分析工具，用于打拿极
(dynode) 与阳极 (anode) 信号的时间匹配、muon 候选事例筛选、特征量 / PE 计算、
可视化与结果输出。

## 目录结构

```
config/            # YAML 参数配置（analysis.yaml / data_source.yaml）
src/muon_analysis/ # 核心包（模块化实现）
scripts/           # 命令行入口与示例数据生成
tests/             # pytest 单元测试
output/            # 默认输出目录
docs/              # 需求、实施计划、交付、架构、批量结果与路径清单等文档
```

## 安装

```bash
pip install -e ".[dev]"
```

需求运行（真实数据）：`waveform_analysis` 与 `pmtdata` 包（参考 `examples/`）。

## 用法

### CLI

```bash
# 分析单个 run（默认 waveform_analysis 后端 + pmtdata gain）
python scripts/run_analysis.py 00179

# 多个 run / 通配符
python scripts/run_analysis.py 00179 00180
python scripts/run_analysis.py '00*' --parallel

# 使用自定义配置、输出目录
python scripts/run_analysis.py 00179 --config config/analysis.yaml --out-dir output/foo

# 仅绘制指定 anode record_id 波形
python scripts/run_analysis.py 00179 --plot-ids 2000,2001

# 缓存管理
python scripts/run_analysis.py --show-cache
python scripts/run_analysis.py --clear-cache
```

### 离线示例数据（无需 waveform_analysis / pmtdata）

```bash
# 生成示例 run 数据
python scripts/sample_data.py --run-id 00179 --out /tmp/muon_demo

# 用 npy 后端 + SQLite gain 数据库离线分析
python scripts/run_analysis.py 00179 \
    --data-root /tmp/muon_demo \
    --data-format npy \
    --relaxed-filters \
    --gain-backend sqlite --gain-path /tmp/muon_demo/gains.db
```

## 分析 Pipeline 与架构

> 详细版（含架构图、各阶段算法约定、模块-代码对照、排查路径、配置表）：
> **[docs/muon_analysis_architecture.md](docs/muon_analysis_architecture.md)**

数据流（单 run）：`runinfo → read → match → filter → features/PE → plot → output`

```
输入 run_id清单 ─► config(CLI>用户>默认+参数哈希)
                 ─► io/runinfo   runinfo.json 发现/解析(runtype 自动探测)
                 ─► io/readers   waveform_analysis | npy | hdf5
                 ─► io/data      RunData: 按 board 分离 dynode(1)/anode(0)
                 ─► matching     时间匹配: dynode +16ns → 按channel merge_asof → dt∈[0,30]
                 ─► filtering    asym 噪声剔除 + 长度/段面积(大脉冲) + 高度阈值
                 ─► features/gain/pe  积分窗口策略 + 电荷→PE(pe_fact/gain)
                 ─► plotting     波形图 + 统计分布图
                 ─► output       <out-dir><run_id>/{CSV, .npz, .png, metadata}
                 ─► cache        /tmp/muon_analysis (run_id+参数哈希, 匹配缓存)
```

各阶段处理细节（模块-代码对照、算法约定、时间关系、常见问题排查）见上述文档，
其中关键算法约定：

1. **时间匹配**：dynode 全局迁移 `+16 ns`（`dynode_shift_ns`），按 channel 用
   `merge_asof(backward)` 最近匹配，保留 `dt = t_dyn_shifted − t_ano ∈ [0,30] ns`。
   实测 146 候选：原始 `dynode_time − anode_time ∈ [-16, 0]`（dynode 提前）。
2. **候选筛选**：波形不对称度（`asym`）噪声剔除、波形长度/段面积筛选（大脉冲）、
   可选高度阈值。
3. **特征量 / PE**：按配置积分窗口策略（默认固定窗口，预留寻峰算法接口）计算面积，
   据 PMT SPE gain 换算为 PE。
4. **输出**：每个 run 独立目录 `<out-dir><run_id>/`（run_id 补零），含
   事例级 CSV（带 `parameter_version` / `gain_db_version` 溯源列）、`.npy` 波形片段、统计分布 `.png`。

## 配置要点

- 所有可调参数集中于 `config/analysis.yaml`。
- 积分窗口策略：`features.integral_window_mode`（`fixed` / `peak_finder`，
  后者为预留寻峰算法接口）。
- PMT gain 数据库：`gain_db.backend`（`pmtdata` / `sqlite` / `csv`）。
- 缓存位于 `/tmp/muon_analysis/`，键为 `run_id + 参数哈希`。

## 测试

```bash
python -m pytest tests/
```
