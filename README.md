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

# 指定 peak/事例序号绘制（筛选前验证图）
python scripts/run_analysis.py 00179 --plot-peaks 0,1,2

# PMT pattern（COG 位置重建 + 三维径迹）
python scripts/run_analysis.py 00179 --pattern /path/to/pattern.json

# 缓存管理
python scripts/run_analysis.py --show-cache
python scripts/run_analysis.py --clear-cache
```

### 离线示例数据（无需 waveform_analysis / pmtdata）

```bash
# 生成示例 run 数据（含增益库与 PMT pattern，用于 COG/径迹演示）
python scripts/sample_data.py --run-id 00179 --out /tmp/muon_demo \
    --gain-db /tmp/muon_demo/gains.db --pattern /tmp/muon_demo/pattern.json

# 用 npy 后端 + SQLite gain 数据库离线分析（含 COG 与径迹重建）
python scripts/run_analysis.py 00179 \
    --data-root /tmp/muon_demo \
    --data-format npy \
    --relaxed-filters \
    --gain-backend sqlite --gain-path /tmp/muon_demo/gains.db \
    --pattern /tmp/muon_demo/pattern.json
```

## 分析 Pipeline 与架构

> 详细版（含架构图、各阶段算法约定、模块-代码对照、排查路径、配置表）：
> **[docs/muon_analysis_architecture.md](docs/muon_analysis_architecture.md)**

数据流（单 run）：`runinfo → read → match → cluster(peaks) → plot(验证) → features/PE → sum(anode_sum/dynode_sum) → filter → cog → track → output`

```
输入 run_id清单 ─► config(CLI>用户>默认+参数哈希)
                 ─► io/runinfo   runinfo.json 发现/解析(runtype 自动探测)
                 ─► io/readers   waveform_analysis | npy | hdf5
                 ─► io/data      RunData: 按 board 分离 dynode(1)/anode(0)
                 ─► matching     时间匹配: dynode +16ns(No-Field) → 按channel merge_asof → dt∈[0,40]
                 ─► clustering   100ns 窗口聚合为 peaks (多 anode + 多 dynode)
                 ─► plotting     筛选前验证图(逐对 + 叠加) + 统计分布图
                 ─► features/gain/pe  peak级特征(area/height/rise/width) + 电荷→PE
                 ─► sum          anode_sum/dynode_sum: 各通道按 pulse_start 对齐逐点求和
                 ─► filtering    peak 级 muon 候选筛选(基于 sum 波形参数: height/width/rise_time/width_ns/面积)
                 ─► cog/track    PMT pattern + COG 重心 + 1µs 切片三维径迹
                 ─► output       <out-dir><run_id>/{CSV(含 peaks_id/cog_x/cog_y/height/width_ns...), .npz(含 anode_sum/dynode_sum), .png, metadata}
                 ─► cache        /mnt/data/tmp/muon_analysis (run_id+参数哈希, 匹配/聚类缓存)
```

各阶段处理细节（模块-代码对照、算法约定、时间关系、常见问题排查）见上述文档，
其中关键算法约定：

1. **时间匹配**：dynode 全局迁移 `+dynode_shift_ns`（可配置；00183/No-Field 实测原始
   dynode−anode dt 中位数 ≈4ns/16ns → 移位后 dt∈[0,40]），按 channel 用
   `merge_asof(backward)` 最近匹配。
2. **波形 sum**：peak 内所有 anode（dynode）通道波形按其各自 `pulse_start` **对齐后逐点
   求和** → `anode_sum`/`dynode_sum`（dynode ×110）；peak 级参数
   （height/width/rise_time/width_ns/width_90area/width_50area/面积/PE）均由 sum 波形计算。
3. **候选筛选**：波形不对称度（`asym`）噪声剔除、波形长度/段面积筛选（大脉冲）、
   可选高度阈值。
4. **特征量 / PE**：按配置积分窗口策略（默认固定窗口，预留寻峰算法接口）计算面积，
   据 PMT SPE gain 换算为 PE。
5. **输出**：每个 run 独立目录 `<out-dir><run_id>/`（run_id 补零），含
   事例级 CSV（带 `parameter_version` / `gain_db_version` 溯源列）、`.npy`/`.npz`
   波形片段（含 anode_sum/dynode_sum）、统计分布 `.png`。

## 配置要点

- 所有可调参数集中于 `config/analysis.yaml`。
- 积分窗口策略：`features.integral_window_mode`（`fixed` / `peak_finder`，
  后者为预留寻峰算法接口）。
- PMT gain 数据库：`gain_db.backend`（`pmtdata` / `sqlite` / `csv`）。
- 缓存位于 `/mnt/data/tmp/muon_analysis/`，键为 `run_id + 参数哈希`。

## 测试

```bash
python -m pytest tests/
```
