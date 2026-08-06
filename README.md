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
docs/              # 需求与实施计划文档
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

## 运行流程

1. `get_runinfo` 从 `runinfo.json` 读取每 run 配置与真实数据路径（`raw_dir`）。
2. 读取 records（`waveform_analysis` / `npy` / `hdf5` 后端），按 `board` 分离
   dynode（board=1）与 anode（board=0）。
3. 时间匹配：dynode 时间迁移 `+16 ns`（或配置值）→ 按 channel 的
   `merge_asof` 最近匹配 → 保留 `dt = t_dyn - t_ano ∈ [min, max]`。
4. 候选筛选：波形不对称度（`asym`）噪声剔除、波形长度 / 段面积筛选
   （大脉冲）、可选高度阈值。
5. 特征量 / PE：按配置的积分窗口策略（默认固定窗口，预留寻峰算法接口）
   计算面积并据 PMT SPE gain 换算为 PE。
6. 输出：事例级 CSV（含 `parameter_version` / `gain_db_version` 溯源列）、
   `.npy` 波形片段、统计分布 `.png`。

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
