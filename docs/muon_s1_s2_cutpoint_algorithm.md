输入：
  - 波形数据 y[t]（已扣除基线）
  - S1峰值位置 s1_peak_idx
  - S1起始位置 s1_start_idx（可选）

↓

步骤1：确定求导起点
    start_idx = s1_peak_idx  （从峰值开始）

↓

步骤2：对峰值右侧求导
    y_prime[i] = y[start_idx + i + 1] - y[start_idx + i]

↓

步骤3A：找导数最小值
    min_idx = argmin(y_prime[min_offset : max_offset])
    s1_end = start_idx + min_idx
    
    OR

步骤3B：找二阶导数过零点
    y_double_prime[i] = y_prime[i+1] - y_prime[i]
    找到首个 y_double_prime > 0 的位置

↓

步骤4：验证结果
    - 检查 s1_end 是否在合理时间范围内
    - 检查 y[s1_end] 是否还在有效幅度范围
    - 检查斜率变化是否显著

↓

输出：S1终点位置 s1_end_idx



def find_s1_endpoint_from_peak(y, s1_peak_idx, min_decay=20, max_decay=500):
    """
    从S1峰值向右求导，找S1终点
    
    参数：
        y: 已扣基线的波形数组
        s1_peak_idx: S1峰值位置（已知）
        min_decay: 最小衰减时间（采样点数）
        max_decay: 最大衰减时间（采样点数）
    
    返回：
        s1_end_idx: S1终点位置
    """
    
    # 1. 从峰值开始向右求导
    start_idx = s1_peak_idx
    y_right = y[start_idx:]  # 峰值右侧的波形
    
    # 2. 计算一阶导数（简单前向差分）
    y_prime = np.diff(y_right)
    
    # 3. 设定搜索范围
    search_start = min_decay
    search_end = min(max_decay, len(y_prime) - 1)
    
    # 4. 在搜索范围内找导数最小值
    idx_min_relative = search_start + np.argmin(y_prime[search_start:search_end])
    
    # 5. 转换回原始波形索引
    s1_end_idx = start_idx + idx_min_relative
    
    # 6. （可选）二阶导数验证
    # y_double_prime = np.diff(y_prime)
    # 检查 s1_end_idx 附近 y'' 是否从负变正
    
    return s1_end_idx


# 使用示例
s1_end = find_s1_endpoint_from_peak(
    y=waveform_data,
    s1_peak_idx=s1_peak,  # 你已经找到的峰值位置
    min_decay=20,
    max_decay=500
)

---

## 实现状态（已落地）

### 算法实现
`src/muon_analysis/pulsefinding.py::find_s1_endpoint_from_peak`

```python
find_s1_endpoint_from_peak(waveform, s1_peak_idx,
                           min_decay=20, max_decay=500,
                           polarity="negative",
                           method="second_derivative")   # 3B（默认）
```
- `polarity="negative"`（anode sum）先翻转，使下降沿为负斜率
- `method`: `"second_derivative"`（3B，二阶差分首个过零）| `"min_derivative"`（3A）

### 配置（`config/analysis.yaml`）
```yaml
muon_s1_s2:
  min_decay: 20            # 搜索窗起点 [峰值后样本]
  max_decay: 500           # 搜索窗终点 [样本]
  method: second_derivative
```

### 分段参数（muon 事例的单独参数，`PeakFeatures`）
切分点：`s1_peak` = anode_sum 的 argmin；`s1_end` = 3B 结果

| 段 | 窗口 |
|---|---|
| **muon S1** | `[a_st, s1_end]` |
| **muon S2** | `[s1_end, end_final]` |

| 字段 | 含义 |
|---|---|
| `muon_s1_start_sample` / `muon_s1_end_sample` / `muon_s2_end_sample` | 三个切分样本 |
| `muon_s1_width_ns` / `muon_s2_width_ns` | `(end − start) × 4 ns` |
| `muon_s1_height` / `muon_s2_height` | `max(|anode_sum|, |dynode_sum|)` 在各自窗口内 |
| `muon_s1_area_ano` / `muon_s1_area_dyn` | anode_sum / dynode_sum 在 S1 窗口的积分（PE）|
| `muon_s2_area_ano` / `muon_s2_area_dyn` | 同上，S2 窗口 |

### Co60 590+ v2 应用结果（muon 组，n=15,524）

| 参数 | 中位 | q25 | q75 |
|---|---|---|---|
| `muon_s1_width_ns` | 104 ns | 100 | 108 |
| `muon_s2_width_ns` | 26,648 ns | 25,776 | 27,412 |
| `muon_s1_height` | 52,258 ADC | 26,318 | 67,896 |
| `muon_s2_height` | 7,221 ADC | 4,143 | 9,699 |
| `muon_s1_area_ano` | 3,649 PE | 1,834 | 4,734 |
| `muon_s1_area_dyn` | 1,766 PE | 653 | 2,643 |
| `muon_s2_area_ano` | 21,621 PE | 13,512 | 32,115 |
| `muon_s2_area_dyn` | 286 PE | 71 | 480 |

切分样本中位：`muon_s1_start_sample=50`、`muon_s1_end_sample=75`、`muon_s2_end_sample=6,738`

**S1 面积占比中位**：**anode 0.141** vs **dynode 0.869**

> ⚠️ **注意**：3B 的 S1 end 落在峰值后 ~25 样本（100 ns），在**饱和削顶**的 muon 波形上
> 捕捉的是"削顶结束"而非 S1/S2 物理边界（目视 ~0.5-1.5 µs）。
> 因此 S1 窗口偏窄：anode 侧 S1 只占 14% 面积（大量前沿面积被划入 S2），
> dynode 侧 S1 占 87%。若需更符合物理的切分，需改用斜率阈值/平台到达判据。

```python
# 使用示例（见上方）

print(f"S1终点位置：{s1_end}")
print(f"S1持续时间：{s1_end - s1_peak} 个采样点")
