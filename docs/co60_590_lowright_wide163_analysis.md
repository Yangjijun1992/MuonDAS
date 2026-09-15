# Co60 590+ lowright 高能最宽事例（width_ns>2000 & width_90area>300ns）

> 数据源：`docs/run7_xe_calibration_run_590_plus.csv`（run 00590-00607，18 个 run，各 3600 s）
> 总采集时长：**64,800 s = 18.00 h**
> 上游筛选：lowright（`width_20_50area<80ns ∧ anode_sum_area>300PE`）+ `height>40000` → 7,543 事例
> 本文档：从中进一步筛选 **`width_ns > 2000` ∧ `width_90area > 300ns`** 的最宽事例

---

## 1. 数量

| 项 | 值 |
|---|---|
| **事例数** | **163** |
| 事例率（18 h） | **9.06 /h** = 0.151 /min = 0.00252 /s |

## 2. 通道数分布

| n_ch | 数量 | 占比 |
|---|---|---|
| **7** | **161** | **98.8%** |
| 6 | 2 | 1.2% |

## 3. 参数中位

| 参数 | 中位 |
|---|---|
| height [ADC] | 68,709 |
| **width_ns [ns]** | **3,848** |
| **width_90area [ns]** | **2,103** |
| width_50area [ns] | 81.3 |
| width_20_50area [ns] | 49.6 |
| anode_sum_area [PE] | 16,913 |
| dynode_sum_area [PE] | 3,197 |

## 4. 逐 run 分布

| run | 数量 |
|---|---|
| 00594 | 14 |
| 00595 | 21 |
| 00598 | 14 |
| 00599 | 14 |
| 00600 | 17 |
| 00602 | 11 |
| 00603 | 17 |
| 00604 | 17 |
| 00605 | 1 |
| 00606 | 23 |
| 00607 | 14 |

> 分布在 11 个 run，run 00606 最多（23）。

## 5. 特征

- 这批是 lowright 高能事例中**最宽**的：`width_ns` 中位 3.8 µs、`width_90area` 中位 2.1 µs
- **98.8% 为 7 通道符合**（161/163）
- 相比 lowright + height>40000 全体（width_ns 中位 776 ns），宽度约为 **5 倍**

## 6. 波形

每个 run 选 3 个事例的 `anode_sum` / `dynode_sum` 波形（含 start/end 标注）：
`/mnt/data/tmp/muon_analysis/co60_590/peak_level/wide163_waveforms/`

## 7. 数据

`/mnt/data/tmp/muon_analysis/co60_590/peak_level/co60_590_lowright_h40000_wide.csv`（163 行）
