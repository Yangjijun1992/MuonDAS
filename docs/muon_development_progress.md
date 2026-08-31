# Muon 分析 - 开发进展与后续开发指南

> 本文档记录开发进展状态、真实数据验证结果与遗留缺口，供**后续开发续接**使用。
> 配套：[需求](muon_dynode_analysis_requirements.md) / [实施计划](muon_dynode_analysis_implementation_plan.md) /
> [架构](muon_analysis_architecture.md) / [交付](muon_analysis_delivery.md)。
>
> 最后更新：2026-08-13

---

## 1. 开发进展总览

基于修订后实施计划完成全部 13 个模块开发，峰值（peak）分析流程贯通：

```
read → match(6ns,[0,40]) → cluster(100ns) → 验证图(逐对/叠加) → features(dynode LP+×110)
     → filter(peak级) → COG → CSV(含cog_x/cog_y) → track(1µs切片) → 面积图/分布图
```

| 里程碑 | 状态 | 证据 |
|---|---|---|
| 数据模型契约（Peak/PeakFeatures/MuonCandidate） | ✅ | models.py |
| clustering / cog / track / pattern 绘图新模块 | ✅ | 对应 .py 文件 |
| 匹配参数统一（6ns / [0,40]）+ README/计划/架构文档同步 | ✅ | 三文档一致 |
| 配置新增 clustering/cog/track 分组 + YAML 数值规范化 | ✅ | config.py `_normalize` |
| CLI：--run-list / --plot-peaks / --pattern / --no-progress | ✅ | run_analysis.py |
| 96 项 pytest + pyflakes 零警告 | ✅ | `python -m pytest tests/` |
| 真实数据端到端（run 00179） | ✅ | 见 §3 |

## 2. 模块完成度对照（计划 13 模块）

| 模块 | 任务项 | 状态 |
|---|---|---|
| 0 架构/目录 | src/scripts/config/output 布局 | ✅ |
| 1 config/CLI | 默认值/覆盖/校验/分析yaml/argparse/--run-list/parameter_version | ✅ |
| 2 io | runinfo/board分离/npy+hdf5/容错 | ✅（hdf5 无测试，P2） |
| 3 matching | 移位/merge_asof/窗口[0,40]/延迟校准 | ✅ |
| 4 clustering | Peak 模型/100ns 算法/配置/输出/测试 | ✅ |
| 5 验证绘图 | 逐对/叠加/批量+指定/筛选前 | ✅ |
| 6 features | 特征量/dynode ×110/PE/分布图 | ✅（新增 width_90area/width_50area/area_ano/area_dyn/rise_time=start→peak） |
| 7 filtering | peak 级判据/配置化/输出/测试 | ✅（判据初步确定：width_90area>1000ns 且 rise_time>80ns，P1 待物理确认） |
| 8 output | CSV(peaks_id/record_id/cog + 全部特征列)/npy/统计图 | ✅ |
| 9 cache | 新路径/哈希/读写/CLI/警告/测试 | ⚠️ 特征未缓存、键不含 gain 版本（P2） |
| 10 cog | pattern 三级来源/重心法/回填 CSV/测试 | ✅ |
| 11 track | 1µs 切片/charge→pmt_id/重心/3D 图/测试 | ✅（anode 切片 COG 径迹演示完成，dynode 记录短需更小切片） |
| 12 pipeline | 主流程/缓存短路/tqdm/容错并行/接线 | ✅ |
| 13 测试文档 | pytest 覆盖/README/示例数据 | ✅ |

**Blockers（§15）解决状态**：COG/pattern 数据结构 ✅（参考 xihu layout）；环境依赖 ✅（真实数据跑通）；
输出规模/命名 ✅（采样控制）；dynode 参数 ⚠️（软件低通取消/硬件 25MHz、global median 基线已用，待物理确认）；
筛选阈值 ⚠️（**初步确定 2026-08-17**：width_90area>1000ns 且 rise_time>80ns，待物理确认固化）。

## 3. 真实数据验证结果（run 00179，run6_Xe）

| 指标 | 值 | 备注 |
|---|---|---|
| 匹配对 | 214,515 | 移位 6ns + [0,40] 窗口 |
| peaks | 30,645 | 每 peak 恒 7 通道（7-PMT 全命中） |
| 候选 | 30,645 | 早期阈值全 None；现筛选判据已初步确定（见 P1） |
| COG 填充 | 30,645/30,645 | runinfo `pos` 坐标；r 均值 3.1mm（近等权趋中） |
| 径迹 | 30,645 | 1µs 切片重建 |
| dynode_area_pe | **均值 -190（异常负值）** | 见 §4.1 基线问题 |

**关键结论**：真实 runinfo mapping 结构（`ch/pmt/pos/label`）与参考 `xihu_fast_analysis`
布局完全一致（ch15=LV2389@(-26.8,17.7)），runinfo pos 路径与内置 FALLBACK_ENTRIES 均适用真实数据。

## 4. 遗留缺口与后续开发清单

### P0 - 数据正确性（影响真实结果）

- [x] **dynode 基线修正**：已通过 `pulse_finder` 的**全局中位数基线**（`baseline_mode=global_median`）解决——此前前 30 样本均值被早发脉冲污染（如 peak 27927 anode 基线 -2231 vs 真值 -29），导致 end 跑飞记录尾；修复后 anode end 落在真实回基线点。

### P1 - 物理定参 / 需求字面项

- [ ] **筛选阈值确认**：**初步确定（2026-08-17）**：`width_90area > 1000 ns` 且 `rise_time > 80 ns`
      （run 00183 筛出 2/1195 长尾事例）。待物理学家复核后固化到 `config['filtering']`，
      并验证对通过/拒绝事例的波形检查。
- [ ] **交互式缩放/平移**（需求 §4）：当前仅保存静态 PNG。若要满足字面需求，
      可引入交互式后端（matplotlib GUI / HTML 页面 / plotly），或明确以降级处理。

### P2 - 接口一致性 / 健壮性

- [ ] **配置分组对齐**：计划约定 `features.dynode_lp/dynode_scale` 分组，实际在
      `plotting` 分组。选择其一：迁配置到 `features`（需同步 architecture 文档），
      或更新计划文档以 `plotting` 为准。
- [ ] **缓存键纳入 gain_db_version**（计划接口 `param_hash = sha1 + gain_db_version`）：
      当前仅 sha1(参数)。若后续缓存特征（依赖 gain）必须加入；当前 match/peaks 缓存无影响。
- [ ] **特征结果缓存**（计划模块九"特征等中间结构"）：可缓存 PeakFeatures（JSON）。
- [ ] **`--debug` 接线**：CLI 已暴露但 pipeline 未使用（可开启详细日志/断点打印）。
- [ ] **hdf5 后端测试覆盖**：readers.py 支持 hdf5，无单测。

## 5. 关键架构决策记录（供后续开发遵循）

| 决策 | 值 | 来源 |
|---|---|---|
| 匹配移位/窗口 | dynode_shift_ns=6, dt∈[0,40] | 统一决策（2026-08-13） |
| 聚类窗口 | clustering.window_ns=100 | 需求 §3 |
| dynode 放大 | ×110（幅度与 area 均隐含 ×110） | 需求 §5 |
| dynode 低通 | null（算法层不滤波）| 硬件 25 MHz 内置 |
| 径迹切片 | track.slice_us=1.0 µs, fs=250e6 | 需求 §9 |
| PMT 位置来源 | 文件 → runinfo pos → 回退（use_fallback） | 参考 layout.py |
| COG 电荷侧 | cog.charge_source=anode | 决策 |
| 绘图采样 | 验证图/径迹/面积图按 num_samples + --plot-peaks | 输出规模控制 |
| CSV 布局 | peaks_id + 各 pmt record_id + cog_x/cog_y + 溯源列 | 需求 §7/§8 |
| 缓存根目录 | /mnt/data/tmp/muon_analysis | 需求 §10 |

## 6. 快速续接指引

```bash
# 环境
conda activate py12          # waveform_analysis / pmtdata 已安装
python -m pytest tests/      # 96 项
python -m pyflakes src/ scripts/ tests/

# 修复 P0 基线问题后，用真实数据复验：
python scripts/run_analysis.py 00179 --out-dir /tmp/mm_out --no-progress
# 检查：dynode_area_pe 均值应转正；COG 仍全填充；径迹数正常
```
