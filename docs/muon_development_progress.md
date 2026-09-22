# Muon 分析 - 开发进展与后续开发指南

> 本文档记录开发进展状态、真实数据验证结果与遗留缺口，供**后续开发续接**使用。
> 配套：[需求](muon_dynode_analysis_requirements.md) / [实施计划](muon_dynode_analysis_implementation_plan.md) /
> [架构](muon_analysis_architecture.md) / [交付](muon_analysis_delivery.md)。
>
> 最后更新：2026-09-22

---

## 0. 最新一轮开发（2026-09-18 ~ 09-22）：peak 级鉴别与 muon S1/S2 搜寻算法

> 本轮把分析主线从「muon 候选筛选」推进到 **peak 级四类信号鉴别** +
> **muon 专属 S1/S2 分段参数化**，并完成 Co60 590+ 全 18 run 的批量重算与系统性验证。

### 0.1 结果总览（Co60 590+，18 run，T = 64,800 s，736,408 peaks）

| 类别 | 数量 | 说明 |
|---|---|---|
| `S1` | **685,024** | 窄脉冲（prompt-like） |
| `muon` | **15,524** | 贯穿 muon 候选 |
| `S2` | **33,608** | 宽、低幅度（delayed-like） |
| `other` | 2,252 | 其余 |

- muon 事例率 **R = 0.2396 s⁻¹ = 14.37 min⁻¹ = 862 h⁻¹**，通量 **122.0 m⁻²s⁻¹**
  （几何期望 167 m⁻²s⁻¹ 的 **73.1%**）——见 `muon_rate_vs_flux.md`
- 7/7 全触发子集（`n_an_pulse=7` 且 `n_dy_pulse=7`）：**5,808 例**（占 muon 的 37.4%）

### 0.2 本轮关键算法决策

| 决策 | 值 / 做法 | 依据 |
|---|---|---|
| **聚类参考点** | 由 record time 改为 **pulse-start time**，窗口 **320 ns** | 对齐更准，run 内一致性更好 |
| **S1 判据** | `width_20_50area < 100 ns` ∧ `width_90area < 1000 ns` | 前沿陡度 + 形状双约束 |
| **muon 判据** | `n_ch ≥ 2` ∧ `height > 15000 ADC` ∧ `width > 2000 ns` ∧ `width_90area > 1000 ns` ∧ `anode_sum_area > 300 PE` | `height` 把 muon 与 S2 分开 |
| **S2 判据** | `width_90area > 1000 ns` ∧ `width > 2000 ns` ∧ `anode_sum_area > 300 PE` ∧ `height < 15000 ADC` | 与 muon 高度互斥 |
| **作废判据** | 基于 `end_first` 的 `s1_width`/`s2_width` 分解 | muon 慢尾使 `end_first` 落到波形末尾 |
| **peak 级 `width` 重定义** | 脉冲跨度 `(end_final − a_st) × 4 ns`（原 `width_ns` 全面废弃改名） | 统一命名，避免与 per-record `Features.width` 混淆 |
| **S1 终点算法** | `find_s1_endpoint_from_peak`，方法可选 **3A(min_derivative) / 3B(second_derivative)**，**选定 3B** | 见 `muon_s1_s2_cutpoint_algorithm.md` |
| **muon S1/S2 参数** | 仅对 `signal_type=="muon"` 计算 12 个分段字段 | 避免污染其它类型 |
| **sum 波形持久化** | 18 个 npz 存 `sum_waveforms/`（523 MB，float32 拼接 + offsets，`np.savez_compressed`） | 离线出图从 ~2 min/run 降到 ~10 s |
| **图像显示缓存坑** | 整幅大图用 read 工具可能返回旧缓存，需 PIL 裁剪到新路径再读 | 验证方法约定 |

### 0.3 系统性的物理发现（影响后续物理结论）

1. **阳极 S1 面积饱和**：`muon_s1_area_dy` vs `muon_s1_area_an` 在 log-log 上强相关
   （r = 0.957），拟合区间 `[10³,4×10³] PE` 内 `y = 1.782x`；超出后脊线向下偏折
   （斜率 1.13 → 2.06 → 3.12），`area_an` 被 ADC 削顶压缩。
2. **S2/S1 强度比**：`muon_s1` 强度中位 34.568 PE/ns，`muon_s2` 0.826 PE/ns，
   比值 **41.82**；×46.9 归一后两条分布大体重合但 S2 更宽、更偏软。
3. **打拿极可分辨性低于阳极**：7/7 子集里阳极 63.0% 满 7 通道，打拿极仅 37.4%。
4. **S2 过阈（×30 > 1695）**：7/7 子集 38,703,595 个采样点中 **91.04%** 过阈；
   基线验证（脉冲前 0.0 ADC、记录末 50 点 6.0 ADC）确认是真实慢分量而非偏置。
5. **打拿极记录窗过短**：全 run 打拿极记录长度中位 **50 样本（0.2 µs）**，
   对 S2 窗（中位 6,704 样本）的覆盖率中位仅 **1.4%**；仅极个别事例
   （如 run600 peaks_id=36092）打拿极也是长窗。
6. **`muon_s1_height_an` 削顶上限** ~1.038×10⁵ ADC（487 例堆积在 103k–104k）。

### 0.4 本轮产物

- **代码**：`signal_id.py`（新增）、`features._fill_muon_segments`、`sum_store.py`、
  `pulsefinding.find_s1_endpoint_from_peak` / `find_wave_final_end`、
  `models.PeakFeatures` 新增 15 个字段、`config.signal_id` / `muon_s1_s2`
- **脚本**（`scripts/`）：`co60_590_peak_level_v2.py`、`save_sum_waveforms.py`、
  `muon_an_dy_channel_ratio.py`、`muon_s2_over_threshold.py`、
  `plot_muon_s1s2_params.py`、`plot_muon_s2width_vs_s1area.py`、
  `plot_muon_7ch_s1area_2d.py`、`plot_muon_7ch_examples.py`、`plot_muon_s2area_nch7.py`、
  `plot_muon_s2area_median_waveforms.py`、`plot_muon_s2over80_examples.py` 等
- **文档**：`peak_width_algorithms.md`、`muon_s1_s2_cutpoint_algorithm.md`、
  `muon_s2_over_threshold.md`、`muon_rate_vs_flux.md`、`other_muon_candidates_params.md`、
  `end_first_muon_s1_issue.md`
- **数据**：`peak_level_v2/co60_590_peak_level_v2.csv`（736,408 行）、
  18 个 `run_XXXXX.csv`、`sum_waveforms/*.npz`、`muon_an_dy_channel_ratio.csv`、
  `muon_7ch_s2_over1695.csv`、`docs/figures/` 下约 30 张图
- **测试**：**117 passed**（`tests/test_signal_id.py` 覆盖四类判据与 muon↔S2 高度互斥）；
  `python -m pyflakes src/ scripts/ tests/` **零警告**

### 0.5 muon S1/S2 搜寻算法流程（代码级）

```
compute_peak_features(peak, run_data, gain_db, config)          # features.py
  │
  ├─ 1. compute_peak_summed_waveforms()  各通道按 pulse_start 对齐逐点求和
  │      → anode_sum / dynode_sum（dynode 每通道先 ×113）
  │
  ├─ 2. find_sum_pulse_bounds()          → a_st（anode_sum 脉冲起点）
  │      → muon_s1_start_sample
  │
  ├─ 3. find_wave_final_end()            → end_final（波形最终终点）
  │      → muon_s2_end_sample
  │
  ├─ 4. find_s1_endpoint_from_peak(anode_sum, s1_peak,
  │        min_decay=20, max_decay=500, method=second_derivative)
  │      s1_peak = argmin(anode_sum)
  │      3A: argmin(diff)  |  3B: 首个 d²>0 过零点      → muon_s1_end_sample
  │
  ├─ 5. classify_signal(feats, n_channels, config)      → signal_type
  │
  └─ 6. if signal_type == "muon":  _fill_muon_segments()
         S1 = [a_st, s1_end]      → width_ns / height_an·dy / area_an·dy
         S2 = [s1_end, end_final] → width_ns / height_an·dy / area_an·dy
         （非 muon 一律保持 0）
```

**运行批量 peak level**：

```bash
python scripts/co60_590_peak_level_v2.py      # 18 run → peak_level_v2/
python scripts/save_sum_waveforms.py          # 18 npz（523 MB）
```

---

## 1. 开发进展总览

基于修订后实施计划完成全部 13 个模块开发，峰值（peak）分析流程贯通：

```
read → match(16ns No-Field/4ns 00183,[0,40]) → cluster(pulse-start, 320ns) → 验证图(逐对/叠加)
     → features(sum 基准, dynode 逐通道×113, 无软件低通) → signal_id(S1/muon/S2/other)
     → muon S1/S2 分解(3B) → filter(peak级) → 输出(CSV/npz/PNG)    [COG/径迹为独立后续阶段]
```

| 里程碑 | 状态 | 证据 |
|---|---|---|
| 数据模型契约（Peak/PeakFeatures/MuonCandidate） | ✅ | models.py |
| clustering / cog / track / pattern 绘图新模块 | ✅ | 对应 .py 文件 |
| 匹配参数统一（16ns/4ns / [0,40]）+ README/计划/架构文档同步 | ✅ | 三文档一致 |
| 配置新增 clustering/cog/track 分组 + YAML 数值规范化 | ✅ | config.py `_normalize` |
| CLI：--run-list / --plot-peaks / --pattern / --no-progress | ✅ | run_analysis.py |
| 96 项 pytest + pyflakes 零警告 | ✅ | `python -m pytest tests/` |
| 真实数据端到端（run 00179） | ✅ | 见 §3 |
| **peak 级参数 sum 化 + dynode_scale=113 + 单位 ns（2026-08-31/09-01）** | ✅ | features.py/models.py，107 pytest |
| **No-Field 全流程验证 + 48 muon 候选 + 架构图解文档** | ✅ | muon_algorithm_architecture.md / muon_peak_screening_results.md |
| **聚类参考改 pulse-start + 320ns 窗口（2026-09-18）** | ✅ | clustering.py，107 pytest |
| **S1/S2/muon/other 四类鉴别（2026-09-20）** | ✅ | signal_id.py，117 pytest |
| **muon S1/S2 分段参数 12 项 + 3A/3B 选型（09-19/20）** | ✅ | features._fill_muon_segments，见 §0 |
| **`width_ns` → `width` 全面替换（peak 级脉冲跨度）** | ✅ | models/features/output/signal_id/config/scripts |
| **Co60 590+ 18 run 批量重算（v2）+ sum 波形持久化** | ✅ | peak_level_v2/（736,408 peaks，523 MB npz） |
| **muon 率→通量、S2 过阈统计、an/dy 通道比等系统性分析** | ✅ | 5 篇新文档 + ~30 张图，见 §0 |

## 2. 模块完成度对照（计划 13 模块）

| 模块 | 任务项 | 状态 |
|---|---|---|
| 0 架构/目录 | src/scripts/config/output 布局 | ✅ |
| 1 config/CLI | 默认值/覆盖/校验/分析yaml/argparse/--run-list/parameter_version | ✅ |
| 2 io | runinfo/board分离/npy+hdf5/容错 | ✅（hdf5 无测试，P2） |
| 3 matching | 移位/merge_asof/窗口[0,40]/延迟校准 | ✅ |
| 4 clustering | Peak 模型/100ns 算法/配置/输出/测试 | ✅ |
| 5 验证绘图 | 逐对/叠加/批量+指定/筛选前 | ✅ |
| 6 features | 特征量/dynode ×113/sum 基准/PE/分布图 | ✅（sum 波形为 peak 参数唯一基准；width 为脉冲跨度、rise_time/width_*area ×4ns；dynode 逐通道 ×113 先放大再 sum；area_dyn ×1；**muon S1/S2 分段 12 项仅对 muon 计算**） |
| 7 filtering | peak 级判据/配置化/输出/测试 | ✅（判据已固化：n_ch≥7 ∧ height>15000 ∧ anode_sum_area>10000 PE ∧ width_ns>5000 ns → No-Field 48 候选；**新增 `signal_id` 四类鉴别取代旧 filter 判据，见 §0**） |
| 8 output | CSV(peaks_id/record_id/cog + 全部特征列)/npy/统计图 | ✅ |
| 9 cache | 新路径/哈希/读写/CLI/警告/测试 | ⚠️ 特征未缓存、键不含 gain 版本（P2） |
| 10 cog | pattern 三级来源/重心法/回填 CSV/测试 | ✅ |
| 11 track | 1µs 切片/charge→pmt_id/重心/3D 图/测试 | ✅（anode 切片 COG 径迹演示完成，dynode 记录短需更小切片） |
| 12 pipeline | 主流程/缓存短路/tqdm/容错并行/接线 | ✅ |
| 13 测试文档 | pytest 覆盖/README/示例数据 | ✅ |

**Blockers（§15）解决状态**：COG/pattern 数据结构 ✅（参考 xihu layout，当前为独立阶段）；环境依赖 ✅（真实数据跑通）；
输出规模/命名 ✅（采样控制）；dynode 参数 ✅（软件低通取消/硬件 25MHz、`dynode_scale=113` 每通道先放大再 sum、`area_dyn` ×1）；
筛选阈值 ✅（**已固化 2026-09-01**：n_ch≥7 ∧ height>15000 ∧ anode_sum_area>10000 PE ∧ width_ns>5000 ns → No-Field 48 候选）。

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

- [x] **筛选阈值确认（已固化 2026-09-01）**：`n_channels ≥ 7` ∧ `height > 15000` ADC ∧
      `anode_sum_area > 10000` PE ∧ `width_ns > 5000` ns（AND）→ No-Field 4,682 个 7ch peaks
      筛出 **48 候选**（run 401→10、402→12、403→15、404→11）；候选参数分布/波形见
      `muon_algorithm_architecture.md` 步骤 8 与 `muon_peak_screening_results.md` §9。
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
| 匹配移位/窗口 | dynode_shift_ns=16（No-Field）/ 4（00183）/ **-16（Co60 590+）**, dt∈[0,40] | 实测 dt 中位数 |
| 聚类窗口/参考 | clustering.window_ns=**320**，参考点为 **pulse-start time** | 需求 §3 + 2026-09-18 重构 |
| peak 级 `width` | 脉冲跨度 `(end_final − a_st) × 4 ns`（旧 `width_ns` 已废弃） | 2026-09-20 统一命名 |
| peak 级鉴别 | `signal_id` 四类互斥：S1 / muon / S2 / other | 见 §0，取代旧 filter 判据 |
| muon S1/S2 切点 | `find_s1_endpoint_from_peak`，method=**second_derivative(3B)** | 3A/3B 对比见专用文档 |
| muon S1/S2 参数 | 仅 `signal_type=="muon"` 计算，12 个字段 | 避免污染其它类型 |
| sum 波形持久化 | `sum_store.save_sum_npz/load_sum_npz`，float32 拼接 + offsets | 离线复用 |
| dynode 放大 | ×113（dynode_scale；逐通道先 ×113 再 sum；area_dyn ×1） | 实测 anode:dynode 比值 ~230 |
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
