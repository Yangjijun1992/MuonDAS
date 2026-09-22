# Muon 分析算法架构（Pipeline 逐步图解）

> 本文档按数据处理 Pipeline 的**关键步骤**组织：每一步给出**算法说明、关键参数、
> 对应代码、实测验证图**（特征图 / 参数图 / 代表性波形）。
>
> 当前版本对应 **Co60 590+ 18 run（run 00590-00607，T = 64,800 s）v2 处理**
> —— 数据目录 `/mnt/data/tmp/muon_analysis/co60_590/peak_level_v2/`，
> 共 **736,408 peaks**。
>
> 配套：[架构总览](muon_analysis_architecture.md) / [需求 §6.1-6.2](muon_dynode_analysis_requirements.md) /
> [开发进展 §0](muon_development_progress.md) / [peak 宽度算法](peak_width_algorithms.md) /
> [muon S1/S2 切点算法](muon_s1_s2_cutpoint_algorithm.md) / [S2 过阈统计](muon_s2_over_threshold.md) /
> [muon 率与通量](muon_rate_vs_flux.md)

---

## Pipeline 总览

```
runinfo 发现 → 读取波形(anode/dynode 分 board) → 时间匹配(anode↔dynode, dt∈[0,40]ns)
   → 聚类成 peak(pulse-start 参考, 320ns 窗口) → 脉冲边界/终点寻峰(pulsefinding)
   → sum 波形(anode_sum/dynode_sum, 按 pulse_start 对齐逐点求和)
   → peak 级参数(height/width/rise/width_*area/面积/PE)
   → 信号鉴别(S1 → S2 → muon → other)
   → muon 专属 S1/S2 切割(S1=[a_st,s1_end], S2=[s1_end,end_final])
   → 输出(CSV / npz / PNG)
```

| 步骤 | 模块 | 产物 | 本文档 |
|---|---|---|---|
| 1 | `io/runinfo.py` + `io/readers*` | RunData（board 分离 anode=0 / dynode=1）| [§1](#步骤-1数据读取io) |
| 2 | `matching.py` | 匹配对（dt 分布）| [§2](#步骤-2时间匹配anode↔dynodematching) |
| 3 | `clustering.py` | `Peak`（多 anode + 多 dynode）| [§3](#步骤-3聚类成-peakclustering) |
| 4 | `pulsefinding.py` | 脉冲起止、S1 终点、波形最终终点 | [§4](#步骤-4脉冲边界与终点pulsefinding) |
| 5 | `features.compute_peak_summed_waveforms` | `anode_sum` / `dynode_sum` | [§5](#步骤-5sum-波形compute_peak_summed_waveforms) |
| 6 | `features.compute_peak_features` | peak 级参数（sum 基准）| [§6](#步骤-6peak-级参数compute_peak_features) |
| 7 | `signal_id.classify_signal` | `signal_type`（S1/S2/muon/other）| [§7](#步骤-7信号鉴别s1--s2--muon--other) |
| 8 | `features._fill_muon_segments` | `muon_s1_*` / `muon_s2_*` 共 12 项 | [§8](#步骤-8muon-s1s2-切割) |
| 9 | `output.py` + `sum_store.py` | CSV / npz / PNG | [§9](#步骤-9输出与持久化) |

---

## 步骤 1：数据读取（io）

**算法**：`get_runinfo()` 发现并解析 `runinfo.json`（runtype 自动探测），
`read_data()` 用 `waveform_analysis` / `npy` / `hdf5` 后端读取，按 **board** 分离
（anode=board 0，dynode=board 1）组装为 `RunData`。波形**已在读取层扣除基线**
（`processed == waveform`）。

**关键参数**：`data_source.data_root`、`data_source.data_format`（`waveform_analysis` | `npy` | `hdf5`）。

**代码**：`src/muon_analysis/io/runinfo.py`、`io/readers.py`、`io/data.py`

---

## 步骤 2：时间匹配（anode↔dynode，matching）

**算法**：dynode 全局时间迁移 `+dynode_shift_ns`（修正通道延迟），再按 **channel**
用 pandas `merge_asof(direction="backward")` 做最近匹配，保留
`dt = t_dynode − t_anode ∈ [min_diff_ns, max_diff_ns]` 的配对。

```
t_dynode' = t_dynode + dynode_shift_ns          # 全局迁移
pair = merge_asof(dynode, anode, by="channel", direction="backward")
keep if min_diff_ns <= dt <= max_diff_ns
```

**关键参数**：

| 参数 | 值 | 说明 |
|---|---|---|
| `matching.sample_interval_ns` | 4 | 4 ns/样本 |
| `matching.dynode_shift_ns` | 16（配置默认）| No-Field 实测 dt 中位 ≈16 ns |
| | **−16** | **Co60 590+ / run7_Xe 使用值** |
| `matching.min_diff_ns` / `max_diff_ns` | 0 / **40** | 匹配窗 [0, 40] ns |
| `matching.channel_delay_ns` | {} | 逐通道延迟校准（可空）|

**实测验证（Co60 590+ v2，18 run，876,885 匹配对）**：

![Co60 590+ v2 匹配前后 dt 分布 + 逐通道](figures/co60_590_v2_matched_dt.png)

| 量 | 值 |
|---|---|
| 原始 dt 中位（未移位）| **32.00 ns** |
| 移位（−16 ns）后中位 | **16.00 ns** |
| 落在 `[0, 40]` ns 窗内 | **100.00%** |
| 逐通道中位 | ch9 = 16 / ch10 = 12 / ch11 = 8 / ch12 = 8 / ch13 = 12 / ch14 = 12 / ch15 = 12 ns |

> 记录 `time` 字段以 4 ns 为步长，故移位后 dt 呈 4 ns 量化台阶；
> 逐通道中位相差 ≤ 8 ns，说明全局移位后各通道一致性可接受。

数据：`co60_590/matched_dt_{raw,shifted}.npy`、`matched_dt_summary.csv`、
`matched_dt_by_channel.csv`；脚本 `scripts/co60_590_dt_distribution.py`。

**匹配对波形核对**（同一 channel、同一事例的 anode 与 dynode 叠加；`rawdyn` 版为
dynode 原始 ×1 波形）：

![run 00401 匹配对叠加（dynode ×113）](figures/matching_pairs_overlay_run401.png)

![run 00401 匹配对叠加（dynode 原始 ×1）](figures/matching_pairs_overlay_rawdyn_run401.png)

**代码**：`src/muon_analysis/matching.py::match_events` / `get_matched_indices_by_channel`

---

## 步骤 3：聚类成 peak（clustering）

**算法**：把匹配对聚成 `Peak`。**聚类参考点是 pulse-start time 而非 record time**：

```
ref(pair) = min( pulse_start_time(anode), pulse_start_time(dynode) )
pulse_start_time = record.time + pulse_start_sample × 4 ns
```

按 `ref` 升序扫描，若当前 pair 的 `ref` 超过当前 peak 的 anchor 超过
**`clustering.window_ns`** 则开启新 peak（贪心、anchor 基准）。

**关键参数**：`clustering.window_ns = 320`（= 80 样本）

> 早期版本用 record time + 100 ns 窗口。改为 pulse-start 参考 + 320 ns 后，
> 同一事例的通道归属更稳定（record time 受触发抖动影响，pulse-start 更接近物理时刻）。

**Peak 数据模型**：`peaks_id`、`start_time_ns`/`end_time_ns`、`anode_records`、
`dynode_records`、`match_rows`、`channels`（`models.Peak`）。

**代码**：`src/muon_analysis/clustering.py::cluster_peaks`、
`_pulse_start_reference_times`

---

## 步骤 4：脉冲边界与终点（pulsefinding）

`pulse_finder()` 对每条波形定位脉冲起止（anode 负脉冲、dynode 先翻正），
`compute_peak_start_end()` 把边界写回每条 `PeakRecord` 的
`pulse_start_sample` / `pulse_end_sample`（供步骤 5 的对齐求和与步骤 7 的鉴别使用）。

在 peak 级 sum 波形上还有三个关键位置：

| 函数 | 输出 | 说明 |
|---|---|---|
| `find_sum_pulse_bounds` | `a_st`（`muon_s1_start_sample`）| anode_sum 脉冲起点 |
| `find_s1_endpoint_from_peak` | `s1_end`（`muon_s1_end_sample`）| **S1 终点 == S2 起点** |
| `find_wave_final_end` | `end_final`（`muon_s2_end_sample`）| 波形最终终点 |

**`find_s1_endpoint_from_peak(waveform, s1_peak_idx, min_decay, max_decay, polarity, method)`**

```
s1_peak = argmin(anode_sum)
搜索窗 = [s1_peak + min_decay, s1_peak + max_decay]        # 默认 [20, 500] 样本

3A  method="min_derivative"      : y'[i] = y[i+1] - y[i] → s1_end = argmin(y')
3B  method="second_derivative"   : y''[i] = y'[i+1] - y'[i] → s1_end = 首个 y'' > 0
```

**关键参数**：`muon_s1_s2.min_decay=20`、`max_decay=500`、`method=second_derivative`（3B）

> 3A/3B 的逐例对比与选型依据见
> [`muon_s1_s2_cutpoint_algorithm.md`](muon_s1_s2_cutpoint_algorithm.md)。

**代码**：`src/muon_analysis/pulsefinding.py`

---

## 步骤 5：sum 波形（compute_peak_summed_waveforms）

**算法**：peak 内所有 anode（dynode）通道波形按**各自 `pulse_start_sample` 对齐**
（公共参考 `SUMMED_REF = 50` 样本，保留峰前基线）后**逐点求和** →
`anode_sum` / `dynode_sum`。

**dynode 侧每个通道先 ×`plotting.dynode_scale`(113) 再叠加**；原始 ×1 求和保留为
`dynode_sum_raw`。由于各通道波形长度不同，sum 数组长度由宽度最大的通道决定。

**关键参数**：`plotting.dynode_scale = 113`、`SUMMED_REF = 50`、
`plotting.dynode_lp_cutoff_hz = null`（硬件 25 MHz 低通已内置，算法层不再滤波）

**代码**：`src/muon_analysis/features.py::compute_peak_summed_waveforms`、
`side_sum`、`SideSummed`

**peak 级 sum 波形对比示例**：

![peak 级 anode_sum / dynode_sum 对比（run 00401）](figures/sum_compare_peak10077_run00401.png)

![peak 级 sum 波形（另一例）](figures/sum_compare_peak000_run00401.png)

**对齐一致性验证**（各通道 sum 起始点与参考脉冲起点的差值分布）：

![sum 起始点差值分布](figures/sum_start_delta_histogram.png)

> 中位 0 ns，86.8% 落在 |Δ| ≤ 4 ns —— 对齐方法可靠。

---

## 步骤 6：peak 级参数（compute_peak_features）

**算法**：所有 peak 级参数**统一由 sum 波形计算**（单位 ns 的时间量均 ×4 ns）：

| 参数 | 定义 | 单位 |
|---|---|---|
| `height` | max(\|anode_sum\|, \|dynode_sum\|) 高度 | ADC |
| **`width`** | **脉冲跨度** `(end_final_sample − a_st) × 4` | ns |
| `rise_time` | anode_sum 的 start → peak × 4 | ns |
| `width_90area` | anode_sum 上含 **90% 面积**的宽度 × 4 | ns |
| `width_50area` | 含 50% 面积的宽度 × 4 | ns |
| `width_20_50area` | 从 20% 到 50% 面积的宽度 × 4 | ns |
| `area_ano` / `area_dyn` | **叠加前逐通道**原始（×1）面积之和 | raw ADC·samples |
| `anode_area_pe` / `dynode_area_pe` | 同上 × mean-gain 的 PE（**无放大**）| PE |
| `anode_sum_area` / `dynode_sum_area` | sum 波形**全波形**积分 × mean-gain（dynode 含 ×113）| PE |
| `wave_len_samples` | sum 数组长度 | 样本 |
| `n_anode_saturated` | 触到 ADC 削顶上限的 anode 通道数 | — |

> ⚠️ **`width_ns` 已废弃**：旧名 `width_ns` 与 per-record `Features.width`（半高计数）
> 易混淆，现已统一为 **`width` = peak 级脉冲跨度**。
> `width` / `width_90area` / `width_50area` / `width_20_50area` 的算法细节见
> [`peak_width_algorithms.md`](peak_width_algorithms.md)。

**PE 换算**：`PE = charge × pe_fact / mean_gain`，
`pe_fact = (2/16384) × 4e-9 / (50 × 1.6e-19) / 1e6`。

**逐 PMT 原始积分**：`anode_area_per_pmt` / `dynode_area_per_pmt`（×1）与
`anode_area_pe_per_pmt` / `dynode_area_pe_per_pmt`（× 该通道自身 gain）。

**关键参数**：`features.baseline_samples=10`、`rise_time_low/high=0.1/0.9`、
`features.saturation.anode_clip_adc=−14700`、`gain_db.backend`（`pmtdata`/`sqlite`/`csv`）

**代码**：`src/muon_analysis/features.py::compute_peak_features`、`gan`

**Co60 590+ v2 全量 peak 参数 2D 面板**（height / width / width_90area / width_20_50area
vs `anode_sum_area` 等）：

![Co60 590+ v2 全量 peak 参数 2D 面板](figures/co60_590_v2_2d_panels.png)

---

## 步骤 7：信号鉴别（S1 → S2 → muon → other）

**算法**：`classify_signal(peak_features, n_channels, config)` 判定信号类型。
**检查顺序固定为 `S1 → S2 → muon → other`，不可更改**；三类判据**互斥**。

| 顺序 | 类型 | 判据（AND）|
|---|---|---|
| 1 | **`S1`** | `width_20_50area < 100 ns` ∧ `width_90area < 1000 ns` |
| 2 | **`S2`** | `width_90area > 1000 ns` ∧ `width > 2000 ns` ∧ `anode_sum_area > 300 PE` ∧ `height < 15000 ADC` |
| 3 | **`muon`** | `n_ch ≥ 2` ∧ `height > 15000 ADC` ∧ `width > 2000 ns` ∧ `width_90area > 1000 ns` ∧ `anode_sum_area > 300 PE` |
| 4 | **`other`** | 其余，或被可选门控 `long_wave_min_samples` 排除（当前 `null` = 关闭）|

**关键参数**：`signal_id.long_wave_min_samples`、`signal_id.{s1,s2,muon}.*`
（各自的 `n_channels` 门控 `null` = 不限制）

**代码**：`src/muon_analysis/signal_id.py`（`_is_s1` / `_is_s2` / `_is_muon` /
`_channel_gate_ok` / `classify_signal`）

### 判别效果（Co60 590+ v2，736,408 peaks）

| 类别 | 数量 | 占比 |
|---|---|---|
| `S1` | **685,024** | 93.02% |
| `S2` | **33,608** | 4.56% |
| `muon` | **15,524** | 2.11% |
| `other` | 2,252 | 0.31% |

### 各类的参数分布

**S1 类**（`width_20_50area` / `width_90area` 双窄）：

![S1 类 peak 参数 2D 面板](figures/co60_590_v2_s1_2d_panels.png)

**S2 类**（非 S1 **且** `height < 1.5×10⁴` ADC）：

![S2 类 peak 参数 2D 面板](figures/co60_590_v2_s2_2d_panels.png)

**S2 类中 `width > 10 µs` 的子集**（n = 17,337 / 33,608；灰色虚线标出各项 cut）：

![S2 且 width > 10 µs 的 peak 参数 2D 面板](figures/co60_590_v2_s2_w10us_2d_panels.png)

该子集的 **`n_ch` 分布**与 S2 全体、muon 类的对比：

![n_ch: S2 / long S2 / muon](figures/co60_590_v2_s2_w10us_nch.png)

| `n_ch` | S2 全体 (33,608) | S2 `width>10 µs` (17,337) | muon (15,524) |
|---|---|---|---|
| 1 | **90.52%** | **87.40%** | 0% |
| 2 | 7.45% | 9.39% | 7.85% |
| 3 | 1.87% | 2.97% | 11.80% |
| 4 | 0.16% | 0.24% | 8.21% |
| 5 | — | — | 4.28% |
| 6 | — | — | 4.86% |
| **7** | — | — | **63.01%** |

> **长 S2 子集与 muon 类的多重度完全不同**：前者 87.4% 为单通道，后者 63.0% 为
> 七通道且**从不为单通道**（muon 判据要求 `n_ch ≥ 2`）——两者不是同一类物理事例。

**muon 类**（非 S1 **且** `height > 1.5×10⁴` ADC **且** `n_ch ≥ 2`）：

![muon 类 peak 参数 2D 面板](figures/co60_590_v2_muon_2d_panels.png)

**S1 与 S2 的通道多重度对比**：

![n_ch: S1 vs S2](figures/co60_590_v2_nch_s1_vs_s2.png)

**S1 / S2 的 anode-vs-dynode sum 面积**：

![S1: anode_sum_area vs dynode_sum_area](figures/co60_590_v2_s1_anode_vs_dynode_sum_area.png)

![S2: anode_sum_area vs dynode_sum_area](figures/co60_590_v2_s2_anode_vs_dynode_sum_area.png)

**边界参数扫描**：

![width_90area vs anode_sum_area](figures/w2050area_vs_anodesum_area_v2.png)

![width vs anode_sum_area](figures/width_vs_anodesum_area_v2.png)

---

## 步骤 8：muon S1/S2 切割

**算法**：**仅对 `signal_type == "muon"` 的 peak** 计算 `muon_s1_*` / `muon_s2_*`
字段（`features._fill_muon_segments()`，其它类型一律保持 0 —— 已校验 720,884 个
非 muon peak 的 12 个字段全为 0）。

```
S1 = [a_st, s1_end]          a_st      = muon_s1_start_sample
S2 = [s1_end, end_final]     s1_end    = muon_s1_end_sample   (S1 终点 == S2 起点)
                             end_final = muon_s2_end_sample
```

每个区段在阳极与打拿极两侧分别给出 **width / height / area**，共 **12 个字段**：

| 字段 | 含义 |
|---|---|
| `muon_s1_width_ns` / `muon_s2_width_ns` | 段宽 = Δsample × 4 ns |
| `muon_s1_height_an` / `muon_s2_height_an` | anode_sum 段内最大 \|幅度\| |
| `muon_s1_height_dy` / `muon_s2_height_dy` | dynode_sum 段内最大 \|幅度\| |
| `muon_s1_area_an` / `muon_s2_area_an` | anode_sum 段内积分 × gain → PE |
| `muon_s1_area_dy` / `muon_s2_area_dy` | dynode_sum 段内积分 × gain → PE |

**关键参数**：`muon_s1_s2.min_decay=20`、`max_decay=500`、`method=second_derivative`

**代码**：`src/muon_analysis/features.py::_fill_muon_segments`

### S1/S2 参数分布（n = 15,524 muon）

![muon S1/S2 参数 2D 相关](figures/co60_590_v2_muon_s1s2_2d.png)

![低面积组（area_an < 2.5e3 PE）的 2D 相关](figures/co60_590_v2_muon_s1s2_2d_lowarea.png)

**光强（area/width，单位 PE/ns/PMT）**：`muon_s1` 中位 **34.568 PE/ns**、
`muon_s2` 中位 **0.826 PE/ns**（差 **41.82 倍**）；归一 ×46.9 后两条分布大体重合，
但 S2 更宽、更偏软。

![muon S1/S2 光强分布](figures/co60_590_v2_muon_s1s2_intensity_liny.png)

> `muon_s1_rise = (S1 peak − muon_s1_start) × 4`（n_ch=7 子集）：中位 **20 ns**
> （q25 16 / q75 24 / q95 28 / q99 372 / max 4516）；100–3000 ns 的慢上升尾部
> 仅出现在高面积组。逐事例数据：`peak_level_v2/muon_s1_rise.csv`。

### 代表性波形

**7/7 全触发事例的 S1 波形**（30 例，x = −0.2 → +1.8 µs）：

![7/7 全触发 muon 的 S1 波形 30 例](figures/co60_590_v2_muon_7ch_s1_examples.png)

**低面积组（`muon_s1_area_an < 2.5e3 PE`，低多重度）**：

![低面积组缩放 1 µs](figures/muon_lowarea_examples_zoom1us.png)

**高面积组（`area_an ≥ 2.5e3 PE`，92.9% 为 7 通道）**：

![高面积组示例波形](figures/muon_higharea_examples.png)

![高面积组缩放 1 µs](figures/muon_higharea_examples_zoom1us.png)

**`muon_s1_area_an` 中位附近（25,969 PE）的 peak 级波形 30 例**：

![中位附近 peak 级波形（log y）](figures/co60_590_v2_muon_s2area25969_peak_waveforms.png)

![中位附近 peak 级波形（linear y）](figures/co60_590_v2_muon_s2area25969_peak_waveforms_linear.png)

**S2 低高度事例**：

![S2 低高度示例（run 595）](figures/s2_lowheight_examples_run595.png)

### muon 专属参数的专题分析

| 专题 | 图 | 结论 |
|---|---|---|
| `area_dy` vs `area_an`（7/7 子集 n=5,808）| ![子集 2D](figures/co60_590_v2_muon_7ch_s1area_dy_vs_an.png) | log-log r = 0.957；`[10³,4×10³]` 区间 `y = 1.782x`；更高面积脊线下折（**阳极饱和**）|
| `muon_s2_width_ns` vs `muon_s1_area_an` | ![s2width vs s1area](figures/co60_590_v2_muon_s2width_vs_s1area.png) | 无相关；宽度被记录长度饱和主导 |
| an/dy 触发通道数比 | ![an/dy ratio](figures/co60_590_v2_muon_an_dy_ratio.png) | 阳极 63.0% 满 7 通道，打拿极仅 37.4%；比值中位 1.167，49.6% 为 1 |
| S2 采样值分布与过阈统计 | ![S2 过阈](figures/co60_590_v2_muon_7ch_s2_over1695.png) | ×30 后 1695 ADC 阈值：**91.04% 采样点过阈** |
| S2 面积（n_ch=7）| ![S2 面积](figures/co60_590_v2_muon_s2_area_nch7.png) | anode 中位 25,969 PE（单峰，2.6 decade）；dynode 中位 374 PE（长尾，5.7 decade）|
| S2 过阈 >80% 的 dynode 波形 | ![S2>80% dynode](figures/co60_590_v2_muon_s2over80_dynode_examples.png) | 27 例满足；打拿极仅覆盖 S1 尖峰 |

---

## 步骤 9：输出与持久化

**CSV**（每 run 一份 + 合并）：`run_XXXXX.csv` → `co60_590_peak_level_v2.csv`
（**736,408 行**），含 `run_id`/`peaks_id`/`n_ch`/`n_anode`/`n_dynode`/
全部 peak 级参数 / `signal_type` / 12 个 `muon_*` 字段。

**sum 波形持久化**：18 个 npz 存 `peak_level_v2/sum_waveforms/run_XXXXX.npz`
（约 **523 MB**），`np.savez_compressed` 存储（float32 拼接 + offsets，无 pickle）。

| 接口 | 说明 |
|---|---|
| `sum_store.save_sum_npz()` / `load_sum_npz()` | 读写 |
| 返回内容 | `{peaks_id, sum_ref, anode_sums:{id: array}, dynode_sums:{id: array}}` |

> 持久化后离线出图从 ~2 min/run 降到 **~10 s**（无需重读原始数据）。

**代码**：`src/muon_analysis/output.py`、`sum_store.py`；
批量脚本 `scripts/co60_590_peak_level_v2.py`、`scripts/save_sum_waveforms.py`

---

## 附录 A：已知系统性限制（解读结果必读）

| # | 限制 | 影响 |
|---|---|---|
| 1 | **3B 的 `s1_end` 是削顶伪影** | 饱和削顶波形上 3B 落在峰值后 ~25 样本（~100 ns），目视 S1/S2 转折在 ~0.5–1.5 µs → S1 窗口偏窄（阳极侧 S1 面积仅占 ~14%，打拿极侧 ~87%）|
| 2 | **`width` / `muon_s2_width_ns` 被记录长度饱和** | muon 在 ~27 µs 处形成水平带，不能当真实脉冲宽度 |
| 3 | **`muon_s1_height_an` 被 ADC 削顶** | 上限 ~1.04×10⁵ ADC（487 例堆积在 103k–104k）|
| 4 | **打拿极记录窗普遍很短** | 记录长度中位 **50 样本（0.2 µs）**；7/7 子集里 `dynode_sum` 中位 121 样本，对 S2 窗（中位 6,704 样本）覆盖率中位仅 **1.4%** → 打拿极侧 S2 统计不可与阳极侧直接比较 |
| 5 | **阳极 S1 面积饱和** | `area_an` 在 `area_dy ≳ 10⁴ PE` 后被压缩，不能表征真实光量 |

**对应诊断图**：

![S1 终点（3B）伪影全景](figures/issue_end_first_full.png)

![S1 终点（3B）伪影放大](figures/issue_end_first_zoom.png)

![长 peak 的 a_st / s1_end / end_final 位置诊断](figures/long_peaks_diagnosis.png)

> 详细分析见 [`end_first_muon_s1_issue.md`](end_first_muon_s1_issue.md)、
> [`other_muon_candidates_params.md`](other_muon_candidates_params.md)、
> [`muon_s2_over_threshold.md`](muon_s2_over_threshold.md)。

---

## 附录 B：逐 PMT 标定发现（No-Field 时期，仍然适用）

**No-Field 全部 anode/dynode 匹配对（n=74,702，run 00401-00405）逐 PMT 积分分布**：

![逐 PMT anode/dynode 积分 2D 直方图 + 比值](figures/perpmt_2dhist_all_pairs.png)

**发现 anode/dynode 比值呈双峰——对应不同 PMT**：

![逐 PMT 比值双峰分离（ch9 vs ch10-15）](figures/perpmt_bimodal_ratio.png)

- ch9：ratio 中位 **~114**，拟合斜率 ~88
- ch10-15：ratio 中位 **~300**，拟合斜率 ~250–265

> `dynode_scale = 113`（LED 小信号标定）是全局平均取值；逐 PMT 存在真实分群。
> 该分析取代了旧版「全局比值 ~230 / 2D 拟合斜率 147」的合成描述——后者把所有 PMT
> 混在一起，掩盖了 ch9 vs ch10-15 的分群。

**48 个 muon 候选（No-Field）的参数分布**（历史结果，筛选判据已由步骤 7 取代）：

![No-Field 7ch peak 参数分布](figures/peak_params_distributions.png)

![48 候选 peak 级参数分布](figures/selected48_params_distributions.png)

![候选示例 run 402 peak 10996](figures/candidate_example_peak10996_run402.png)

---

## 配置速查（`config/analysis.yaml`）

| 配置组 | 关键键 | 当前值 |
|---|---|---|
| `matching` | `sample_interval_ns` | 4 |
| | `dynode_shift_ns` | 16（Co60 590+ 用 **−16**）|
| | `min_diff_ns` / `max_diff_ns` | 0 / 40 |
| `clustering` | `window_ns` | **320** |
| `plotting` | `dynode_scale` | **113** |
| | `dynode_lp_cutoff_hz` | null（硬件 25 MHz，无软件低通）|
| `signal_id` | `long_wave_min_samples` | null（关闭）|
| | `s1.w20_50area_max_ns` / `w90area_max_ns` | 100 / 1000 |
| | `s2.w90area_min_ns` / `width_min_ns` / `anode_sum_area_min_pe` / `height_max_adc` | 1000 / 2000 / 300 / 15000 |
| | `muon.n_channels_min` / `height_min_adc` / `width_min_ns` / `w90area_min_ns` / `anode_sum_area_min_pe` | 2 / 15000 / 2000 / 1000 / 300 |
| `muon_s1_s2` | `min_decay` / `max_decay` / `method` | 20 / 500 / `second_derivative` |
| `features` | `baseline_samples` / `rise_time_low` / `rise_time_high` | 10 / 0.1 / 0.9 |
| | `saturation.anode_clip_adc` | −14700 |
| `gain_db` | `backend` | `pmtdata` / `sqlite` / `csv` |
