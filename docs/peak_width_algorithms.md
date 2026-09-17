# Peak 级 width 参数计算算法

> 代码：`src/muon_analysis/features.py`（`compute_peak_features` / `compute_features` /
> `width_to_fraction_area`）、`src/muon_analysis/pulsefinding.py`（`find_sum_pulse_bounds` /
> `find_wave_final_end`）
> 采样间隔 `interval_ns = matching.sample_interval_ns = 4 ns`

## 0. 前提：peak 的 sum 波形与两个端点

所有 peak 级 width 都基于 **对齐叠加波形** `anode_sum` / `dynode_sum`
（`compute_peak_summed_waveforms`：各通道按自身 `pulse_start_sample` 对齐到
`ref = max(SUMMED_REF=50, max pulse_start)` 后逐点求和；dynode 逐通道 ×`dynode_scale`）。

三个关键样本索引：

| 符号 | 来源 | 含义 |
|---|---|---|
| `a_st` | `find_sum_pulse_bounds(anode_sum)` → `pulse_finder` | anode_sum 的脉冲**起点**（前沿回到基线处）|
| `end_first_sample` | 同上 → `a_ed` | anode_sum 的**首次回基线**点 |
| `end_final_sample` | `max(find_wave_final_end(anode_sum), find_wave_final_end(dynode_sum))` | 整条 peak 波形的**最后回基线**点（`find_wave_final_end` = 最后一个 \|值\| < `end_baseline_tol`(20 ADC) 的样本；若从未回基线则取波形末样本）|

## 1. `width`（FWHM，样本计数法）

`features.py::_fwhm_samples` → 在 `compute_peak_features` 中 `width = sf_a.width × 4 ns`

```
above = (anode_sum − baseline) × direction >= 0.5 × |peak_amp − baseline|
width_samples = count_nonzero(above)          # 整条波形中所有超半高样本的个数
width [ns]    = width_samples × 4
```

- `direction = −1`（anode 负极性），`peak_amp = anode_sum` 的极值（argmin）
- `baseline` = 前 `baseline_samples`(10) 个样本的均值
- **注意**：这是**计数**而非连续跨度——若波形有多个峰/振荡，所有超半高的样本都被计入
- `rise_time` 同样取自 `anode_sum`：`(argmin − pulse_start) × 4 ns`

## 2. `width_ns`（全脉冲时长）

```
width_ns = (end_final_sample − a_st) × 4 ns        # end_final > a_st 时；否则 0
```

- 从 anode_sum 起点到**整条波形最后回基线**点
- ⚠️ **对 μ 子事例被记录长度饱和**：μ 子拖尾在记录结束前不归零 →
  `end_final_sample ≈ 波形末端` → `width_ns ≈ wave_len_samples × 4`
  （见 `docs/other_muon_candidates_params.md` §5）

## 3. `width_90area` / `width_50area`（面积累积宽度）

`features.py::width_to_fraction_area` → 在 `compute_peak_features` 中调用，
窗口固定为 `[a_st, end_final_sample]`：

```
proc   = anode_sum − baseline                 # baseline = mean(前 10 样本)
seg    = |proc[a_st : end_final_sample]|
total  = sum(seg)                             # 脉冲区总面积
cum    = cumsum(seg)
target = frac × total                         # frac = 0.9 或 0.5
idx    = interp(target, cum, arange(len(cum))) + 1.0   # 线性插值定位
width  = idx × 4 ns
```

- 物理含义：从 `a_st` 起，**累积到总面积的 frac 倍**所需的宽度
- `frac = 0.9` → `width_90area`；`frac = 0.5` → `width_50area`
- `+1.0` 为半开区间修正；`end <= start` 或 `total <= 0` 时返回 NaN

## 4. `width_20_50area`（20%→50% 面积累积宽度）

```
w20 = width_to_fraction_area(..., frac = 0.2)   # 样本数
w50 = width_to_fraction_area(..., frac = 0.5)
width_20_50area = (w50 − w20) × 4 ns            # w20/w50 任一为 NaN 时取 0
```

- 物理含义：从 20% 面积累积点走到 50% 面积累积点所需的宽度
- **对上升沿形状敏感**（前 50% 面积的分布），与 `width_90area`（覆盖到 90%）互补

## 5. 汇总表

| 参数 | 公式 | 参考端点 | 敏感对象 |
|---|---|---|---|
| `width` [ns] | `count(\|anode_sum−bl\| ≥ 0.5·peak) × 4` | 无（全波形计数）| 半高以上的总样本数 |
| `width_ns` [ns] | `(end_final − a_st) × 4` | a_st → end_final | 全脉冲时长（μ 子被记录长度饱和）|
| `width_90area` [ns] | `idx(0.9·total) × 4` | a_st → end_final | 90% 面积累积宽度（含拖尾）|
| `width_50area` [ns] | `idx(0.5·total) × 4` | a_st → end_final | 50% 面积累积宽度 |
| `width_20_50area` [ns] | `(idx(0.5·total) − idx(0.2·total)) × 4` | a_st → end_final | **前段上升/前沿形状** |

## 6. 用于信号分类的 width

| 分类 | 使用的 width | 阈值 |
|---|---|---|
| **S1** | `width_20_50area` + `width_90area` | `< 100 ns` ∧ `< 1000 ns` |
| **muon** | `width_ns` + `width_90area` | `> 2000 ns` ∧ `> 1000 ns` |
| **S2** | `width_ns` + `width_90area` | `> 2000 ns` ∧ `> 1000 ns`（另需 `height < 1.5e4`）|

**判别力排序**（Co60 590+ v2 实测）：
- `width_20_50area` / `width_90area` —— **最有效**（S1 与 muon/S2 在此清晰分离）
- `width_ns` —— 对 μ 子被记录长度饱和，区分力弱
- `width`（FWHM 计数）—— 受振荡影响，未用于分类
