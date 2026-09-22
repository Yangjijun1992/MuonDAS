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

数据流（单 run）：`runinfo → read → match → cluster(peaks) → plot(验证) → sum(anode_sum/dynode_sum) → features/PE → signal_id(S1/S2/muon/other) → muon S1/S2 分解 → filter → cog → track → output`

```
输入 run_id清单 ─► config(CLI>用户>默认+参数哈希)
                 ─► io/runinfo   runinfo.json 发现/解析(runtype 自动探测)
                 ─► io/readers   waveform_analysis | npy | hdf5
                 ─► io/data      RunData: 按 board 分离 dynode(1)/anode(0)
                 ─► matching     时间匹配: dynode +dynode_shift_ns → 按channel merge_asof → dt∈[0,40]
                 ─► clustering   pulse-start 320ns 窗口聚合为 peaks (多 anode + 多 dynode)
                 ─► pulsefinding peak 起止 / S1 终点(3A·3B) / 波形最终终点
                 ─► plotting     筛选前验证图(逐对 + 叠加) + 统计分布图
                 ─► features/gain/pe  peak级特征 + sum 波形 + 电荷→PE
                 ─► signal_id    peak 级鉴别 → S1 | muon | S2 | other
                 ─► muon S1/S2   muon 专属: S1=[a_st,s1_end], S2=[s1_end,end_final]
                 ─► filtering    peak 级 muon 候选筛选(基于 sum 波形参数)
                 ─► cog/track    PMT pattern + COG 重心 + 1µs 切片三维径迹
                 ─► output       <out-dir><run_id>/{CSV, .npz(anode_sum/dynode_sum), .png, metadata}
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

## peak 级信号鉴别（S1 / S2 / muon / other）

每个 peak 在 `compute_peak_features()` 内完成特征计算后，由
[`signal_id.classify_signal()`](src/muon_analysis/signal_id.py) 判定信号类型
（三类判据**互斥**，按 S1 → muon → S2 顺序检查，均不满足则 `other`）。
所有判别量都取自 **sum 波形**（`anode_sum`/`dynode_sum`），阈值集中在
`config/analysis.yaml` 的 `signal_id` 分组：

| 类型 | 判据（AND） |
|---|---|
| **`S1`** | `width_20_50area < 100 ns` **且** `width_90area < 1000 ns` |
| **`muon`** | `n_ch ≥ 2` **且** `height > 15000 ADC` **且** `width > 2000 ns` **且** `width_90area > 1000 ns` **且** `anode_sum_area > 300 PE` |
| **`S2`** | `width_90area > 1000 ns` **且** `width > 2000 ns` **且** `anode_sum_area > 300 PE` **且** `height < 15000 ADC` |
| **`other`** | 其余（或被可选门控 `long_wave_min_samples` 排除，当前 `null`=关闭） |

`signal_id.{s1,s2,muon}` 下还可分别设置 `n_channels` 门控（`null`=不做通道数限制）。

### 为什么用 width-cut 而不是 `end_first`

早期用「`end_first` 宽度分解 S1/S2」的判据已**作废**：muon 慢尾使 sum 波形长期
达不到「回到基线」判据，`end_first` 落到波形末尾，prompt 与 delayed 分量无法据此
分离（详见 [`docs/end_first_muon_s1_issue.md`](docs/end_first_muon_s1_issue.md)）。
改用 **`width_90area` / `width_20_50area` / `height` / `anode_sum_area` / `n_ch`**
后，四类在高统计量样本上分离清晰：Co60 590+ 18 run（736,408 peaks）得到
**S1=685,024 / muon=15,524 / S2=33,608 / other=2,252**。

### muon 专属的 S1/S2 分解

只有 `signal_type == "muon"` 的 peak 才会计算 `muon_s1_*` / `muon_s2_*` 字段
（`features._fill_muon_segments()`，其它类型保持 0）。分解点由
[`pulsefinding.find_s1_endpoint_from_peak()`](src/muon_analysis/pulsefinding.py) 给出：

```
S1 = [a_st, s1_end]           # a_st        = anode_sum 脉冲起点
S2 = [s1_end, end_final]      # s1_end      = S1 终点 (== S2 起点)
                              # end_final   = 波形最终终点 find_wave_final_end()
```

`s1_end` 的搜法由 `muon_s1_s2.method` 选择（搜索窗 `[s1_peak+min_decay, s1_peak+max_decay]`）：

| 方法 | 说明 |
|---|---|
| **`second_derivative`（3B，默认）** | 从 S1 峰值向右求一阶差分，再求二阶差分**首个过零点** |
| `min_derivative`（3A） | 一阶差分的**最小值**点 |

每个区段在阳极与打拿极两侧分别给出 **width / height / area** 共 12 个字段：
`muon_s1_width_ns`、`muon_s2_width_ns`、`muon_s1_height_an/dy`、
`muon_s2_height_an/dy`、`muon_s1_area_an/dy`、`muon_s2_area_dy` —— 见
[`models.PeakFeatures`](src/muon_analysis/models.py)。

> ⚠️ **已知系统性限制**（解读结果时必须留意）
> 1. **3B 的 `s1_end` 是削顶伪影**：在饱和削顶的 muon 波形上，3B 落在峰值后
>    ~25 样本（~100 ns），而目视的 S1/S2 转折在 ~0.5–1.5 µs。因此 S1 窗口偏窄
>    （阳极侧 S1 只占 ~14% 面积，打拿极侧 ~87%）。
> 2. **`width` / `muon_s2_width_ns` 对 muon 被记录长度饱和**（~27 µs 处的水平带）。
> 3. **`muon_s1_height_an` 被 ADC 削顶**限制在 ~1.04×10⁵。
> 4. **打拿极记录窗普遍很短**（中位 121 样本 ≈ 0.48 µs，而 S2 窗中位 6,704 样本），
>    打拿极侧的 S2 统计不可与阳极侧直接比较；详见
>    [`docs/muon_s2_over_threshold.md`](docs/muon_s2_over_threshold.md)。

## 配置要点

- 所有可调参数集中于 `config/analysis.yaml`。
- peak 级鉴别：`signal_id`（`s1` / `s2` / `muon` 三组阈值 + 可选 `n_channels` 门控
  + `long_wave_min_samples`）。
- muon S1/S2 分解：`muon_s1_s2.min_decay` / `max_decay` / `method`。
- 聚类窗口：`clustering.window_ns`（默认 320 ns，以 pulse-start 为参考）。
- 积分窗口策略：`features.integral_window_mode`（`fixed` / `peak_finder`，
  后者为预留寻峰算法接口）。
- PMT gain 数据库：`gain_db.backend`（`pmtdata` / `sqlite` / `csv`）。
- 缓存位于 `/mnt/data/tmp/muon_analysis/`，键为 `run_id + 参数哈希`。

## 相关文档

| 文档 | 内容 |
|---|---|
| [需求规格](docs/muon_dynode_analysis_requirements.md) | 完整算法流程需求 |
| [开发进展](docs/muon_development_progress.md) | 进展状态与续接指南 |
| [架构总览](docs/muon_analysis_architecture.md) | 模块-代码对照、配置表 |
| [peak 宽度算法](docs/peak_width_algorithms.md) | `width` / `width_90area` / `width_20_50area` 定义 |
| [muon S1/S2 切点算法](docs/muon_s1_s2_cutpoint_algorithm.md) | 3A/3B 对比与选型 |
| [S2 过阈统计](docs/muon_s2_over_threshold.md) | 7/7 子集的 S2 过阈分析 |
| [muon 率与通量](docs/muon_rate_vs_flux.md) | 事例率 → 通量换算 |

## 测试

```bash
python -m pytest tests/
```
