# 问题记录：`end_first` 落在波形末端 —— muon S1/S2 宽度分解失效

> 状态：**已解决（见 §7）** —— S1 改用 width cut 判别，`end_first` 宽度分解作废
> 命名：信号标签早期为 `muon_s1` / `muon_s2`，后统一重命名为 **`S1` / `S2`**（§7 起使用新名；
> §1–§6 描述问题发现时的旧状态，其中的标签即今 `S1` / `S2`）
> 发现于：Co60 590+ v2 重跑（18 run，新 clustering：pulse-start 参考 + 320ns 窗口）
> 相关代码：`src/muon_analysis/pulsefinding.py`（`find_sum_pulse_bounds` / `find_pulse_boundaries`）、
> `src/muon_analysis/features.py`（`compute_peak_features`）、`src/muon_analysis/signal_id.py`

## 1. 现象

peak level 新增参数中：

- `end_first_sample` = anode_sum 的寻峰"首次回基线"点（`find_sum_pulse_bounds` → `a_ed`）
- `end_final_sample` = 整条 peak 波形的最后回基线点（`find_wave_final_end`）
- `muon_s1_width_ns = (end_first − a_st) × 4`
- `muon_s2_width_ns = (end_final − end_first) × 4`

在 18 run 重跑结果（736,408 peaks）中：

| signal_type | 数量 |
|---|---|
| muon_s2 | 7,916 |
| **muon_s1** | **0** |
| other | 728,492 |

长波形（`wave_len_samples > 5000`，24,435 个）实测：

| 参数 | 中位 |
|---|---|
| `muon_s1_width_ns` | **12,864 ns**（≈ 全宽）|
| `muon_s2_width_ns` | 12,084 ns |
| `end_first_sample` | 3,620 |
| `end_final_sample` | 6,709 |

→ `muon_s1_width` 并非"窄前沿"，而是**整个事例宽度**；`muon_s1` 判据（`s1_width ≤ 500ns`）几乎无事例满足。

## 2. 根因

`find_pulse_boundaries`（`pulsefinding.py`）的右端判据是：

> 信号必须**回到基线并保持**：`end` 样本及其后 `end_consecutive` 个样本都需落在
> `end_baseline_tol`（默认 **20 ADC**）以内；否则 `end` 回退为记录末端。

而 **muon 事例的 anode_sum 在前沿尖峰之后存在长拖尾**，拖尾期间信号长期停留在
−200 ~ −3200 ADC，**远低于 ±20 ADC 的回基线容差**，因此寻峰永远找不到"回基线"点，
`end_first` 回退为波形末端（n−1）。

### 证据（run 00595，长波形 7ch 事例）

| peaks_id | len | a_st | end_first | pre_bl | **post_bl** | post>tol |
|---|---|---|---|---|---|---|
| 23 | 6870 | 49 | 2281 | 0.4 | **-213** | 293/300 |
| 141 | 6581 | 49 | 5972 | -0.2 | **-956** | 300/300 |
| 157 | 6690 | 49 | 6336 | 0.6 | **-2364** | 300/300 |
| 426 | 6962 | 49 | 6842 | 1.1 | **-2665** | 300/300 |
| 557 | 7691 | 50 | **403** | 0.3 | **-22** | 172/300 |
| 1410 | 7090 | 49 | **234** | 1.3 | **-1.5** | 89/300 |

- `pre_bl`（脉冲前沿之前的基线）≈ 0 ✓
- `post_bl`（a_st+200 ~ a_st+500）≈ **-200 ~ -3200 ADC** ✗（拖尾）
- `post>tol`：绝大多数样本超出 ±20 ADC 容差
- 仅极少数事例（如 id=557 / 1410，拖尾很小 post_bl≈0）才有真正的"前沿结束"点

## 3. 说明波形

**run 00595，peak_id = 20791**（`len = 7699`，7 通道，height = 103,839 ADC）

- 全波形：`docs/figures/issue_end_first_full.png`
  （`a_st=50`、`end_first=7608`、`end_final=7698`——`end_first` 落在波形末端）
- Zoom-in：`docs/figures/issue_end_first_zoom.png`
  （以"高度衰减至 1/3 峰值"处为中心，x 范围 ±5µs，y 范围 ±height/10 = ±10,384 ADC）
  → 可见前沿尖峰后信号稳定停在 **~-2,500 ADC**，**永不回到 0 基线**

复现脚本：`scripts/plot_end_first_issue.py`（`PEAK_ID = 20791`，`RUN = "00595"`）
诊断脚本：`scripts/diagnose_long_peaks.py`、`scripts/check_sum_baseline.py`

## 4. 影响

1. **`muon_s1` 恒为 0**：`muon_s1_width ≤ 500ns` 判据无法满足。
2. **`muon_s2` 结果不可靠**：`muon_s2_width = end_final − end_first`，
   当 `end_first ≈ end_final`（多数长事例）时宽度≈0；
   当前 7,916 个 `muon_s2` 实际是 dynode 尾部晚于 anode 结束的产物，而非物理 S2 定义。
3. **S1/S2 分解（前沿 vs 拖尾）在有长拖尾的 muon 事例上不可用**。

## 5. 待定方案（需确认"前沿结束（S1 end）"的定义）

1. **局部极小**：取前沿尖峰之后第一个局部极小（不要求回 ±20 基线）。
2. **高度分数**：取信号自尖峰恢复到峰值 X%（如 10% / 20%）处作为 S1 end。
3. **导数/斜率**：取前沿快速下降段结束处（|d/dt| 低于阈值）。
4. **拖尾比例**：以拖尾占比（如 `tail_area / total_area`）定义 S1/S2，而非宽度切分。
5. 其它（待用户指定）。

同时需明确：

- `muon_s1` 是否应对应"**短波形**（无长拖尾）"、`muon_s2` 对应"**长拖尾**"？
- `muon_s1` 的宽度范围阈值应为多少？

## 6. 验证计划

确定 S1-end 算法后：

1. 在 `scripts/plot_end_first_issue.py` 的参考波形（peak_id=20791）上叠加新 S1-end 标记，
   确认其落在**前沿回落段**而非波形末端；
2. 用 `scripts/check_sum_baseline.py` 在长波形样本上统计新 S1-end 的分布；
3. 更新 `signal_id.py` 判据 → 重跑 18 run → 打印新鉴别算法与 signal_type 分布；
4. 更新 example 波形（lowright/upright）与 2D 图。

## 7. 解决（S1 改用 width cut 判别）

`end_first`-based 的 `muon_s1_width` / `muon_s2_width` **判据作废**（参数仍保留用于诊断）。
新判别（`src/muon_analysis/signal_id.py`）：

```
S1    : width_20_50area < 100 ns  AND  width_90area < 1000 ns
S2    : 超出上述任一 cut（S1 的补集）
other : 仅当启用可选门控（long_wave_min_samples / n_channels）且未通过时
```

配置（`config/analysis.yaml`）：

```yaml
signal_id:
  long_wave_min_samples: null # 可选门控，null = 关闭
  s1:
    n_channels: null
    w20_50area_max_ns: 100.0
    w90area_max_ns: 1000.0
  s2:
    n_channels: null
```

### Co60 590+ v2 应用结果（736,408 peaks）

| signal_type | 数量 | 占比 |
|---|---|---|
| **S1** | **685,024** | 93.0% |
| **S2** | **51,384** | 7.0% |
| other | 0 | 0% |

对应 2D 图：`docs/figures/co60_590_v2_s1_2d_panels.png`（S1）、
`docs/figures/co60_590_v2_nons1_2d_panels.png`（non-S1）。

### 验证
- `tests/test_signal_id.py`（7 例：窄事例→S1、超 cut→S2、边界互斥、两个可选门控）
- 参考波形（run **00595**, peak_id=20791）：`w20_50area=10,673.5ns`、`w90area=24,479.2ns`
  → **S2** ✓（宽事例，符合预期）
- 全量测试 114 passed
- 注意：`peaks_id` 是 **per-run** 的（每个 run 从 0 重新编号），跨 run 引用需带 `run_id`
