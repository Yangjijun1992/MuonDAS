# Peak 级数据筛选结果整理（存档）

> **归档日期**：2026-08-18
> **分析区间**：2026-08-13 ~ 2026-08-18
> **数据 run**：`00183`（run6_Xe）
> **环境**：`py12`（`/home/yjj/.conda/envs/py12/bin/python`）
> **作者**：Sisyphus（OhMyOpenCode）
>
> 本文档记录近几日对 peak level 数据的分析、算法演进与筛选结果，供后续筛选阈值标定与物理验证阶段跟进参考。

---

## 0. 目录

1. [数据源与总体流程](#1-数据源与总体流程)
2. [Peak 级参数定义与算法演进](#2-peak-级参数定义与算法演进)
3. [基础统计结果](#3-基础统计结果)
4. [统计分布图（用于信号筛选）](#4-统计分布图用于信号筛选)
5. [长尾事例筛选结果](#5-长尾事例筛选结果)
6. [产物文件清单](#6-产物文件清单)
7. [关键结论与发现](#7-关键结论与发现)
8. [下一阶段建议](#8-下一阶段建议)

---

## 1. 数据源与总体流程

### 1.1 流程概览（波形级 → peak 级）

```
波形匹配 (match, 波形级) → 聚类 (clustering, 100ns 窗口 → peak)
        → 寻峰 (pulse_finder, start/end)
        → 特征提取 (features: area/height/width/rise_time/width_90area/PE)
        → COG 重建 → 径迹重建 → 统计分布 → 长尾事例识别
```

### 1.2 规模数据（run 00183）

| 阶段 | 数量 | 说明 |
|---|---|---|
| 波形匹配对数 | **1,003,975** | anode–dynode 波形级匹配，dt∈[2,38]ns |
| 聚类 peaks | **990,674** | 100ns 窗口聚类 |
| **n_channels == 7 的 peaks** | **1,195** | 7-PMT 全命中（muon 候选）|
| 导出波形总数 | 16,730 | 1195 peaks × 14 记录（7 anode + 7 dynode）|

**manifest.json** 关键字段：

```json
{
  "run_id": "00183",
  "runtype": "run6_Xe",
  "min_channels": 7,
  "total_matched_pairs": 1003975,
  "total_peaks": 990674,
  "selected_peaks": 1195,
  "total_waveforms": 16730,
  "layout_source": "runinfo"
}
```

### 1.3 n_channels 分布（anode × dynode）

峰值级通道分布几乎全为对角（same anode=dynode）：

| anode × dynode | peaks | 占比 |
|---|---|---|
| 1 × 1 | 986,974 | 99.627% |
| 7 × 7 | 1,195 | 0.12%（重点候选）|
| 其余 | — | 其余对角组合 |

---

## 2. Peak 级参数定义与算法演进

以下几日内对 peak 参数与算法进行了多轮定义与修正，是筛选的关键依据。

### 2.1 采样间隔

- 采样间隔 = **4 ns**
- 离散 sample 参数换算为 ns 需 ×4

### 2.2 参数单位对照表

| 参数 | 单位 | 换算为 ns | 说明 |
|---|---|---|---|
| `peak_width` | **样本**（FWHM 计数）| ×4 | 通道半高宽样本数最大值 |
| `peak_rise_time` | **样本**（start→peak 差）| ×4 | 见 §2.4 |
| `width_90area` | **样本**（start→90% 面积）| ×4 | 见 §2.5 |
| `peak_width_ns` | **ns**（end−start 时间窗）| 本身即 ns | 见 §2.3 |

### 2.3 Peak 时间窗 start/end 定义（多轮修正）

- **start** = 各通道波形（anode + dynode 均寻峰）脉冲起点聚合。
- **end**：
  - **anode（负脉冲）**：从**峰值点（peak）向右**，找到**首次回到基线**（|processed| < 20 ADC）的点为 end（`end_consecutive=0`，不加稳定确认）。
  - **dynode（正脉冲）**：`end + 3 点确认`（稳定回基线）。
  - `peak_width_ns = end − start`。

**anode end 修复效果（peak 27927，anode 7 通道）**：

| 通道 | 旧 end | 新 end | 通道 | 旧 end | 新 end |
|---|---|---|---|---|---|
| ch9 | 142 | **66** | ch13 | 84 | **53** |
| ch10 | 79 | **50** | ch14 | 7319 | **88**（原无效→有效）|
| ch11 | 272 | **54** | ch15 | 173 | **70** |
| ch12 | 570 | **88** | | | |

- 修复后 **7/7 anode 通道全部有效**；peak 窗口 median **480 → 204 ns**。

### 2.4 rise_time 定义（最终版）

```
rise_time = peak_index − pulse_start_sample
```
- **anode（负脉冲）**：peak = 波形最负点（argmin）
- **dynode（正脉冲）**：peak = 波形最正点（argmax）
- **两侧都计算**（不再跳过负脉冲）
- 移除早期 10%/90% `_crossing` 机制（`rise_crossing_indices` 保留为弃用占位）

**演进历史**（供追溯）：
1. 早期 10%/90% 交叉：负脉冲扫描区间错误 → anode rise_time 恒为 0（bug）
2. 改为 start→peak：负脉冲跳过 → 仅 dynode 有效
3. **最终版（现行）**：两侧均按 `peak − start`，物理合理（start→peak 短区间）

### 2.5 width_90area 算法（新增参数）

**算法（单波形）**：

```
1. processed = waveform − baseline（稳健基线）
2. total = Σ|processed[start : end]|        # 脉冲区 [start, end] 总面积
3. 从 start 起累加 cum = Σ|processed[start : k]|
4. width_90area = 首个使 cum ≥ 0.9·total 的 (k − start)   # 样本
peak 级 width_90area = max(所有 anode+dynode 通道的 width_90area)
```

实现在 `features.py`：`width_to_fraction_area()`（单波形）+ `_record_width_90area()`（按记录）。

### 2.6 峰值级聚合参数（CSV 列，共 34 列）

`peaks_id, time_ns, channels, anode_record_ids, dynode_record_ids, anode_area_pe, dynode_area_pe, area_ano, area_dyn, peak_height, peak_width, peak_rise_time, peak_width_ns, width_90area, charge_per_pmt, start_time_ns, end_time_ns, cog_x, cog_y, pe_anode_ch9..15, pe_dynode_ch9..15`

- **三层结构**：
  - **第 1 层 Peak 级聚合**（CSV 一行）：上述 34 列
  - **第 2 层 每通道波形特征**（Features）：height、charge、rise_time、width、baseline
  - **第 3 层 记录级**（npz 逐行，7×2 记录）：record_id、channel、time_ns、pulse_start_sample、pulse_end_sample

---

## 3. 基础统计结果

（n = 1195 peaks，7 通道候选）

### 3.1 rise_time 分布

| 指标 | 值 |
|---|---|
| peak 级 median | 6 样本（24ns）|
| 范围 | [4, 49] 样本 |
| 集中 | 5–8 样本（410 / 399 / 188）|

**逐记录分布（npz 全部记录）**：

| 直方图 | n | median | range |
|---|---|---|---|
| `rise_anode_hist` | 8,365（全部 anode 记录）| 4 样本 | [1, 12] |
| `rise_dynode_hist` | 8,189 | 4 样本 | [-6, 21]（dynode 峰值在 start 前的过冲情形）|

注：早期直方图不连续，源于 10%/90% 整数交叉机制；改用 start→peak 后分布连续合理。

### 3.2 width_90area 分布（1195 peaks）

| 指标 | 值 |
|---|---|
| median | 22 样本（88 ns）|
| mean | 44.0 |
| range | [16, 1656] 样本 |
| p25 / p75 / p90 | 20 / 29 / 47 |
| p99 | 606 |

- 主峰集中在 16–23 样本（20/21/22 为峰值：174/177/116）——削顶脉冲主体宽 ~80–90 ns
- 长尾（p99=606，最大 1656=6624ns）对应慢恢复/多峰事件

### 3.3 peak_width_ns 分布（end 修复后）

| 指标 | 修复前 | 修复后 |
|---|---|---|
| median | 480 ns | **204 ns** |
| mean | 3988 ns | 305 ns |
| p90 | 14355 ns | 348 ns |
| range | — | [128, 7940] ns |

### 3.4 area（总电荷）分布

| 字段 | 定义 | peak 27927 示例 | 1195 peaks median |
|---|---|---|---|
| `area_ano` | 所有 anode 通道总电荷（charge 求和，未 PE 标定）| 819,398 | 757,112 |
| `area_dyn` | 所有 dynode 通道总电荷（含 ×110 放大）| 423,974 | 369,611 |
| `anode_area_pe` / `dynode_area_pe` | PE 标定版总电荷 | 5,386.9 / 2,787.3 | — |

### 3.5 Peak 级参数清单示例（peak 27927）

| 参数 | 值 |
|---|---|
| `peak_height` / `peak_width` / `peak_rise_time` | 17,495.8 / 7 / 8 |
| `peak_width_ns` | 2,220（端修复后为 292）|
| `cog_x` / `cog_y` | 0.03 / 1.83 |
| `start_time_ns` / `end_time_ns` | 540 / 1,760 |

---

## 4. 统计分布图（用于信号筛选）

**位置**：`/mnt/data/tmp/muon_analysis/muon_candidates_00183_n7/statistics/`（共 **31 图**）

### 4.1 单位统一（均换算为 ns，样本 ×4）

| 参数 | 原单位 | 现显示 |
|---|---|---|
| `peak_width` | 样本（FWHM）| ×4 → ns（标签 `[ns]`）|
| `peak_rise_time` | 样本 | ×4 → ns |
| `width_90area` | 样本 | ×4 → ns |
| `peak_width_ns` | ns | 不变 |

### 4.2 1D 直方图（27 个参数，n=1195）

- 聚合：`anode_area_pe`、`dynode_area_pe`、`area_ano`、`area_dyn`、`peak_height`、`peak_width`、`peak_rise_time`、`peak_width_ns`、`width_90area`、`cog_x`、`cog_y`
- 逐通道 PE：`pe_anode_ch9~15`、`pe_dynode_ch9~15`（14 个）
- 逐记录 rise：`rise_anode_hist`、`rise_dynode_hist`（2 个）

### 4.3 2D 直方图（用于筛选判定）

| 文件 | x 轴 | y 轴 |
|---|---|---|
| `2d_peak_width_vs_anode_area_pe` | Anode Area [PE] | Peak Width [ns] |
| `2d_peak_width_vs_peak_height` | Peak Height [ADC] | Peak Width [ns] |
| `2d_peak_rise_time_vs_anode_area_pe` | **Anode Area [PE]** | **Peak Rise Time [ns]**（坐标轴已对调）|
| `2d_width_90area_vs_anode_area_pe`（新增）| **Anode Area [PE]** | **Width 90% Area [ns]** |

> 提示：目录中仍保留旧的 `2d_anode_area_pe_vs_peak_rise_time*` 文件（旧轴序，已废弃，新图以 `2d_peak_rise_time_vs_anode_area_pe` 为准）。

---

## 5. 长尾事例筛选结果

### 5.1 筛选条件

| 条件 | 阈值 | 样本换算 |
|---|---|---|
| `peak_rise_time > 60ns` | >60 ns | >15 样本 |
| `width_90area > 1000ns` | >1000 ns | >250 样本 |

### 5.2 单独条件统计（width_90area 长尾）

| 阈值 | 事例数 | 占比 |
|---|---|---|
| > 1000ns（>250 样本）| **31** | 2.59% |
| > 1500ns（>375 样本）| 22 | — |
| > 2000ns（>500 样本）| **15** | — |
| 最大值 | 1656 样本 = **6624 ns** | — |

> 长尾事例（90% 面积宽 > 1µs）约占候选的 2.6%，为慢恢复/多峰结构。

### 5.3 双条件交集（rise >60ns 且 w90 >1000ns）：3 / 1195

保存文件：`muon_candidates_00183_n7/00183_selected_rise60ns_w90_1000ns.csv`

| peaks_id | rise_time(样本/ns) | peak_width_ns | width_90area(样本/ns) | anode_area_pe |
|---|---|---|---|---|
| 392386 | 28 / 112 | 1892 | 364 / 1456 | 4739.6 |
| 532377 | 20 / 80 | 1876 | 373 / 1492 | 4129.6 |
| 542809 | 26 / 104 | 1444 | 286 / 1144 | 3777.5 |

> 注：同时满足两个长尾条件的事例极少——大多数长 `width_90area` 事例 rise 反而短（削顶快脉冲），长 rise 事例的 90% 面积又较早达成。

### 5.4 width_90area > 2000ns：15 事例（已存波形）

**位置**：`muon_candidates_00183_n7/selected_w90_2000ns/`
- `w90_2000ns_events.csv`：15 事例 peak 级参数
- `w90_2000ns_waveforms.npz`：**210 条波形**（15 × 14 记录，含 pulse_start/end）
- `peak{id}_verify_{anode,dynode,compare}*.png`：**45 张验证图**（15 × 3）

**15 个事例（按 width_90area 降序）**：

| peaks_id | width_90area(样本) | rise_time | peak_width_ns | anode_area_pe |
|---|---|---|---|---|
| 186131 | **1656** | 6 | 7940 | 6795 |
| 157292 | 1056 | 5 | 4992 | 6523 |
| 639117 | 849 | 5 | 3980 | 6420 |
| 783468 | 845 | 7 | 4000 | 5482 |
| 978190 | 833 | 7 | 4008 | 3875 |
| 516260 | 817 | 6 | 3816 | 5580 |
| 976729 | 782 | 5 | 3884 | 10068 |
| 27020 | 781 | 5 | 4000 | 11486 |
| 560012 | 648 | 5 | 3456 | 9953 |
| 806070 | 685 | 5 | 3368 | 13908 |
| 420509 | 666 | 7 | 2964 | 4627 |
| 626275 | 659 | 6 | 3276 | 11363 |
| 607185 | 603 | 7 | 2948 | 6109 |
| 729021 | 597 | 5 | 2928 | 13999 |
| 988193 | 581 | 9 | 2820 | 8200 |

**特征观察**：这些事例 rise_time 都很短（5–9 样本，削顶快脉冲），但 peak_width_ns 大（2.8–7.9µs）且 width_90area 长——**大幅值、长恢复/多峰结构**（如 186131 窗口 7.9µs、w90=6.6µs）。

### 5.5 典型事例验证图（双条件 3 个中的 2 个）

**位置**：`validate_00183/selected_longtail/`（各 3 张，共 6 张）

| 文件 | 内容 |
|---|---|
| `peak532377_verify_anode/dynode/compare_*.png` | peak 532377（width_90area 最大，1492ns）|
| `peak392386_verify_anode/dynode/compare_*.png` | peak 392386（宽 1892ns）|

每张图：anode/dynode 叠加 + 7 通道逐一、start(橙)/end(绿)/rise(品红/青) 标记线、peak 窗口(绿)标注。

---

## 6. 产物文件清单

### 6.1 主数据集

**位置**：`/mnt/data/tmp/muon_analysis/muon_candidates_00183_n7/`

| 文件 | 内容 |
|---|---|
| `00183_muon_candidates.csv` | 1195 peaks × 34 列 peak 级参数 |
| `00183_waveforms.npz` | 16,730 条逐记录波形（含 pulse_start/end）|
| `manifest.json` | 数据集元信息 |
| `statistics/` | 31 张统计分布图 |
| `selected_w90_2000ns/` | 15 长尾事例（>2000ns）波形 + 45 验证图 |
| `00183_selected_rise60ns_w90_1000ns.csv` | 双条件 3 事例 |

### 6.2 验证图

**位置**：`/mnt/data/tmp/muon_analysis/validate_00183/`

| 目录/文件 | 内容 |
|---|---|
| `random_peaks/` | 10 个随机 peak × 3 图（含上升沿标记）|
| `selected_longtail/` | 双条件典型事例验证图 |
| `peak27927_verify_*.png` | 代表 peak 三合一验证图 |
| `peak27927_width90area_check.png` | width_90area 可视化（7 面板 anode）|
| `peak934762_{anode,dynode}_rise_*.png` | start→peak rise 区间检查图 |
| `peak{148254,477824}_{overlay,pairs}_*.png` | 叠加 / 逐对图 |
| `00183_peaks_summary.csv` / `00183_stage_summary.json` | 阶段汇总 |

### 6.3 提交记录

| commit | 内容 |
|---|---|
| `910b3f0` | Implement peak-based muon analysis pipeline（初始峰值流程）|
| `2b04079` | Add pulse-finder based peak start/end and verification plots |
| `24e549f` | 验证图窗口按侧重构 + dynode 滤波确认 |

---

## 7. 关键结论与发现

1. **7-PMT 全命中候选**（n_channels=7）仅有 **1,195 / 990,674** peaks（0.12%），是 muon 候选的核心集合。
2. **anode end 算法修复**是本次最重要的修正：从记录尾回退改为"峰值后首次回基线"，使 peak 窗口 median 从 480→204ns，7/7 anode 通道全部有效，`peak_width_ns` 分布大幅收紧。
3. **rise_time 定为 start→peak** 后分布连续物理合理（peak 级 median=6 样本，集中在 5–8）；dynode 偶有过冲（rise 为负值）。
4. **width_90area** 为新增长尾判定参数，主峰集中 88ns 附近，p99=606 样本；是识别慢恢复/多峰事例的有效指标。
5. **长尾事例占比**：width_90area >1µs 约 2.6%，>2µs 有 15 个；这些是大幅值、快 rise、长恢复/多峰结构，需在 muon 筛选时评估是信号还是本底。
6. **双长尾条件交集极小**（3/1195），说明长 rise 与长 width_90area 在物理上负相关（削顶快脉冲的 90% 面积早达成）。

---

## 8. 下一阶段建议

按实施计划，peak 级分析基本完成，下一阶段为 **muon 候选筛选与物理验证**：

1. **筛选阈值标定（核心）**：基于统计直方图（1D + 2D）确定 muon 判据；对比长尾/异常事例与主峰在 area/width/rise_time/PE/COG 各维度分布差异，结合物理预期确定 `filtering.*` 阈值。
2. **筛选实现与真实数据验证**：将阈值写入 `filter_muon_candidates` 配置，比较筛选前后事例数（当前 30645 → 物理筛后），抽查通过/拒绝事例验证图。
3. **筛出事例物理分析**：COG 位置分布、径迹重建质量、事例率与时间分布。
4. **多 run 批处理**：`run_batch.py` 跑多 run，构建统一事例目录，跨 run 一致性检查。
5. **遗留收尾**：hdf5 测试覆盖、`--debug` 接线、特征缓存、配置分组对齐。

---

## 附：相关关键代码位置

- 寻峰：`findpulse_st_ed()`（参考 `docs/peakfinding.md`）
- 特征/rise_time/width_90area：`src/muon_analysis/features.py`
- 统计分布图：`src/muon_analysis/plotting/distributions.py`、`scripts/plot_peak_statistics.py`
- 验证绘图：`src/muon_analysis/plotting/waveforms.py`（`plot_peak_verification`、`plot_peak_rise_check`）
- 聚类/Peak 模型：`src/muon_analysis/clustering.py`

---

## 9. 48 个 muon 候选的 peak 级参数分布（No-Field）

**筛选条件（AND）**：`n_channels ≥ 7`、`height > 15000` ADC、`anode_sum_area > 10000` PE、`width_ns > 5000` ns
→ 从 No-Field 4,682 个 7ch peaks 选出 **48 个候选**（run 401→10、402→12、403→15、404→11）。

### 参数统计（n=48）

| param | median | q25 | q75 | mean | min | max |
|---|---|---|---|---|---|---|
| height [ADC] | 320,620 | 250,930 | 437,633 | 400,861 | 146,280 | 1,831,260 |
| width [ns] | 92 | 83 | 105 | 98 | 56 | 216 |
| rise_time [ns] | 20 | 16 | 24 | 20 | 12 | 32 |
| width_ns [ns] | 5,700 | 5,399 | 6,653 | 6,586 | 5,040 | 18,636 |
| width_90area [ns] | 742 | 648 | 860 | 815 | 492 | 2,124 |
| width_50area [ns] | 84 | 76 | 93 | 89 | 60 | 208 |
| area_ano | 3,176,828 | 2,801,916 | 3,676,989 | 3,416,885 | 1,985,282 | 7,946,273 |
| area_dyn | 26,278 | 20,049 | 35,099 | 32,146 | 11,189 | 140,068 |
| anode_area_pe [PE] | 20,904 | 18,437 | 24,195 | 22,484 | 13,063 | 52,287 |
| dynode_area_pe [PE] | 173 | 132 | 231 | 212 | 74 | 922 |
| anode_sum_area [PE] | 24,305 | 21,332 | 27,679 | 26,141 | 14,842 | 64,945 |
| dynode_sum_area [PE] | 41,265 | 32,236 | 55,032 | 49,977 | 18,028 | 211,958 |

![48 候选 peak 级参数分布](figures/selected48_params_distributions.png)

> 与全体 7ch peaks（n=4,682）对比：候选 height 中位 320k（全体 71k）、width_ns 5.7µs（2.5µs）、
> anode_sum_area 24.3k PE（6.9k PE）——候选显著更"高能 + 宽脉冲"。
> 完整逐事例表：`/mnt/data/tmp/muon_analysis/no_field_peaks/selected_48/selected48_params.csv`。
