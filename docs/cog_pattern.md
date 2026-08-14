# Pattern（PMT 坐标 / 打火模式）信息 —— 代码位置总结

> 本文档为分析 `xihu_fast_analysis` 脚本时，对 "pmt 坐标信息" 与 "pattern 信息"
> 相关代码位置的完整总结（来自对话输出的归档记录）。
>
> 分析对象仓库根目录：`/home/yjj/xihu_fast_analysis/`

---

## 一、PMT 坐标信息

**核心定义文件：`/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py`**（唯一的坐标来源）

| 位置 | 内容 |
|---|---|
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py` L10-88 `FALLBACK_ENTRIES` | **硬编码的 7-PMT 回退几何坐标**（pmt_no → x_mm/y_mm，如 pmt_no 4 中心 (0.0, 0.0)） |
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py` L90-91 `FALLBACK_BY_PMT_ID/PMT_NO` | 按 pmt_id 或 pmt_no 查询坐标的查找表 |
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py` L94-109 `PmtEntry` | 坐标容器 dataclass，`xy_mm` 属性返回 (x, y) |
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py` L112-152 `PmtLayout` | 集合访问器，`pmt_positions` 返回 `{pmt_no: (x,y)}` |
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py` L155-165 `load_pmt_layout` | 优先读 `runinfo.json`，缺失时回退到硬编码几何 |
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py` L168-216 `_layout_from_runinfo` | 从 runinfo.json 的 `channel["pos"]` 解析 `[x, y]` 坐标 |
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/layout.py` L219-225 `_fallback_layout` | 从 FALLBACK_ENTRIES 构建 PmtLayout |

**坐标的使用位置：**

- `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/display.py` L13-16：绘图几何常量（旋转角 30°、边长 21.5mm、内外环半径 39/62mm）
- `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/display.py` L349-416 `_plot_pmt_area_map`：按 `entry.x_mm/y_mm` 画 PMT 方块
- `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/display.py` L419-433 `charge_center_xy`：按面积加权 x/y 计算电荷中心 CoQ
- `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/raw.py` L80/L117 调用 `load_pmt_layout`，L261 传入布局绘图
- `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/__init__.py` L11-16：重新导出 `PmtEntry`、`PmtLayout`、`load_pmt_layout`、`charge_center_xy`
- `/home/yjj/xihu_fast_analysis/tests/test_event_display.py`：测试中内联定义坐标并断言读取

> 注意：全仓库**没有 z 坐标**，几何是纯 2D (x_mm, y_mm)。

---

## 二、Pattern 信息

**重要发现：字面关键词 `pattern`（及"模式"）在整个仓库中完全不存在**——已对全部
.py/.ipynb/.json 等文件做了大小写不敏感搜索，0 处匹配。代码里**没有** Pattern 类、
没有触发模式定义、没有 pattern 匹配模块。

最接近"pattern 信息"（哪几个 PMT 一起打火的多 PMT 击中模式）的代码是**候选事件
选择时隐式推导**出来的：

| 位置 | 内容 |
|---|---|
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/display.py` L130-190 `select_event_candidates` | 从 cache hits 聚类时间簇，记录 `channels` 集合（L159-160）和 `n_channels`，用 `n_channels >= min_channels` 筛选（L161） |
| `/home/yjj/xihu_fast_analysis/xihu_fast_analysis/raw.py` L162-192 `select_raw_candidates` + L324-344 `_append_candidate` | 从 V1725 波形聚类，记录打火的 `pmt_numbers` 集合（L327），同样用最小通道数筛选（L328），L336 累加各 PMT 面积 |
| `area_by_pmt` / `area_pe_by_pmt`（`/home/yjj/xihu_fast_analysis/xihu_fast_analysis/raw.py` L334-336、`/home/yjj/xihu_fast_analysis/xihu_fast_analysis/display.py` L226） | 每个 PMT 的振幅"模式"，导出到 summary JSON 并画成 PMT 面积图 |

**结论**：目前代码里"pattern"这个名称不存在；如果需要命名化的 pattern 信息（比如
每种打火模式的定义/选择），现有代码已经在 `select_event_candidates`
（`/home/yjj/xihu_fast_analysis/xihu_fast_analysis/display.py` L130-190）和
`select_raw_candidates`（`/home/yjj/xihu_fast_analysis/xihu_fast_analysis/raw.py`
L162-192）中算出了 PMT 通道集合，这是最自然的扩展点。

---

*归档来源：对话中对 `/home/yjj/xihu_fast_analysis` 脚本 pmt 坐标信息 / pattern 信息的代码定位总结。*
