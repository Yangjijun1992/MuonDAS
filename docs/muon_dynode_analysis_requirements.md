# Muon 事例筛选、打拿极读出分析与径迹重建 需求规格说明书

> 本文档描述完整的 Muon 分析算法流程。处理顺序：
> 数据读取 → 时间匹配 → 波形聚类(peaks) → 波形可视化与验证 → 事例特征分析 →
> muon 事例筛选 → 结果输出 → PMT pattern + COG 位置重建 → muon 径迹重建。

## 1. 数据读取

- 支持批量传入多个 `run_id`（列表、通配符或外部配置文件），依次读取打拿极(dynode)与阳极(anode)数据。
- 兼容现有 example 脚本的数据格式，自动解析时间戳、波形及必要的元信息。
- 遇到文件缺失、格式错误等情况应输出明确警告并跳过当前 `run`，不中断后续批处理。

## 2. 时间匹配

- 实现打拿极与阳极信号的高精度时间对齐，沿用 example 中的匹配逻辑（dynode 时间移位 + 按通道 `merge_asof` 最近匹配）。
- 支持探测器不同通道间延迟校准参数的外部配置。
- 输出包含配对时间、波形索引等信息的匹配事件列表，供聚类阶段使用。

## 3. 波形聚类（clustering → peaks）

- 在时间匹配之后，将对同一事件的多通道波形按时间聚合成 **peak**：
  - 将 **record time 在 100 ns 范围内**的所有波形组合成一个 `peak`（record time 指波形记录的起始时间戳，仅作为聚类合并判据）。
  - 每个 `peak` 包含**多个 anode 通道的波形**以及**多个 dynode 通道的波形**（同一时间窗内命中的所有通道）。
- 聚类窗口（100 ns）作为可调参数存放于配置文件中。
- 输出 peak 列表：每个 peak 记录 `peaks_id`、时间范围、所含 anode/dynode 通道集合、各通道波形/记录索引，供可视化验证、特征分析与后续筛选使用。
- **peak 时间范围（start/end）定义**：
  - 对 peak 内**所有 anode 与 dynode 通道的波形**分别进行**寻峰**，得到每个通道波形的脉冲起始时间（`pulse_start`）与结束时间（`pulse_end`）。
  - `peak.start` = **所有通道 `pulse_start` 的最小值**；`peak.end` = **所有通道 `pulse_end` 的最大值**。
  - **end 判据**：从脉冲峰值点向右寻找回到基线（`end_baseline_tol`，默认 20 ADC）的位置——anode 取**首次回到基线**即 end；dynode 需 **end 之后连续 3 点保持 ≤20 ADC**（稳定确认，避免瞬时振荡误判）。
  - **dynode 寻峰输入为原始波形**（算法层无软件低通；硬件 25 MHz 低通已内置，`dynode_lp_cutoff_hz=None`），anode 用原始波形。
  - 寻峰算法独立封装、可插拔（当前实现借鉴 `findpulse_st_ed`；`pulse_finder` 接口可替换）。

## 4. 波形可视化与验证（在筛选之前）

- 在 muon 候选事例筛选**之前**进行波形可视化，以便快速检查 peaks 内波形与通道合并是否合理：
  - **逐对绘制**：将每个 `peak` 中所有 anode/dynode 通道对都画出来。
  - **叠加（overlay）**：
    - 将所有 anode 波形进行叠加显示。
    - 将所有 dynode 波形进行叠加显示。
- 支持交互式缩放、平移以检查波形细节；可将图像保存为 `.png`，支持自动批量生成或指定 peak/事例序号绘制。
- 可视化作为筛选前的验证步骤，指导聚类/通道合并参数的合理性判断。

## 5. 事例特征分析（对合并后的 peaks，含 PE 标定）

- 对**所有合并后的 peak 波形数据**计算事例特征：
  - 脉冲面积（charge / area）
  - 脉冲高度（height）
  - 上升时间（上升沿）
  - 宽度等
- **peak 级参数统一由 sum 波形计算**：
  - **sum 波形**：将 peak 内所有 anode（dynode）通道波形按其各自 `pulse_start` **对齐**后**逐点求和**（`anode_sum`/`dynode_sum`；dynode 侧**每个通道先 ×dynode_scale(230) 再叠加**，保留峰前基线 `sum_ref`；原始 ×1 求和保留为 `dynode_sum_raw`）。
  - `height`（= max(anode_sum, dynode_sum) 高度）、`width`（anode_sum FWHM ×4ns）、`rise_time`（anode_sum 的 start→peak ×4ns）、`width_ns`（= (anode_sum_end − anode_sum_start)×4ns）均由 sum 波形计算，时间类参数单位为 **ns**。
  - `width_90area`/`width_50area`：在 anode_sum 上从脉冲起点累积 90%/50% 面积处的宽度（×4ns，单位 ns）。
  - `area_ano`/`area_dyn`：anode_sum/dynode_sum_raw（原始 ×1）在 **[anode_sum start, dynode_sum end]** 区间上的面积。
  - `anode_area_pe`/`dynode_area_pe`：同上区间面积 × mean-gain 的 PE 换算（无放大）。
  - `anode_sum_area`/`dynode_sum_area`：sum 波形**全波形**积分 × mean-gain 的 PE（dynode 侧含 ×230）。
- **rise_time 定义**：从脉冲起点（`pulse_start`）到脉冲峰值点的区间（`peak_index − pulse_start`，×4ns 后以 ns 计）；anode 峰值=最负点、dynode 峰值=最正点，两侧均计算。
- 对于每个 peak 内的 **dynode 波形部分**：
  - **低通滤波**：硬件 25 MHz 已内置；软件低通取消，`dynode_lp_cutoff_hz=None`。
  - **×dynode_scale(230) 放大**：作用于 `dynode_sum`（逐通道先放大再对齐求和）、逐通道 dynode 特征（高度/面积）、`dynode_sum_area`（全波形 PE）。
  - **`area_dyn`/`dynode_area_pe` 不放大**（基于原始 ×1 的 `dynode_sum_raw`，按需求重定义）。
- 调用 **PMT SPE gain 数据库**（根据探测器通道查询增益），将积分电荷换算为光电子数 (PE)。
  - 数据库可为 CSV、JSON 或 SQLite，需支持灵活配置文件路径。
- 生成特征量的统计分布图（如 PE 谱、时间差谱）以验证聚类/筛选条件合理性，图像保存为 `.png`。

## 6. muon 事例筛选

- 在波形可视化验证与特征分析**之后**，根据以上所得的特征信息设置筛选条件，判定每个 peak 是否为 muon 候选事例。
- 筛选基于（但不限于）：幅度阈值、时间符合/聚类窗口、脉冲形状（面积/高度/上升时间/宽度）、PE 相关判据。
- **当前已固化的筛选判据（2026-09-01）**：`n_channels ≥ 7` 且 `height > 15000` ADC 且
  `anode_sum_area > 10000` PE 且 `width_ns > 5000` ns（AND 交集）。No-Field 数据
  （00401-00405，n=4,682 个 7ch peaks）筛出 **48 个 muon 候选**（run 401→10、402→12、
  403→15、404→11）。
- 所有筛选参数（阈值、窗口大小、形状判据等）集中存放于配置文件（YAML/JSON）。
- 输出通过筛选的 muon 候选事例集合（按 peak）及其基本属性。

## 7. 结果输出

- 最终筛选出的波形片段保存为 `.npy` 文件（NumPy 数组），可通过参数控制是否启用该功能。
- **在结果输出之后，保存 muon 事例的信息，包括 peak 级参数**：
  - peak 级区域/面积（area）、高度（height）、宽度（width）等；
  - `peaks_id`；
  - 每个 `pmt_id`（anode/dynode）的 `record_id` 等信息。
- 事例级参数（run_id、event_id、peak 级参数、PE、height、time 等）保存为 CSV 文件，便于后续分析。
- 统计分布图以 `.png` 格式保存至指定目录。

## 8. PMT pattern 导入与 COG 位置重建

> ⚠️ **独立阶段（不在当前冻结的筛选 pipeline 内）**：当前数据分析流程以
> 匹配 → 聚类 → sum 波形 → peak 参数 → 筛选 为主线；COG 位置重建与径迹重建
> 作为后续物理分析阶段单独开展（对应 `cog.py`/`track.py`，算法见架构总览文档）。

- 导入 **pmt pattern 信息**用于 **COG（重心）位置重建**。
- 结合各通道电荷量用重心法计算事件横向位置。
- 输出每个 muon 事例的重建位置（COG）及相关信息。

## 9. muon 径迹重建

- 依据筛选出的 muon 事例的 **dynode 波形**重建 muon 径迹：
  - 将 dynode 合并后的 **peak 级波形进行时间切片**，以 **1 µs** 为一个时间切片。
  - 将每个时间切片内所有 PMT 的 **charge** 信息赋给各自的 `pmt_id`。
  - 结合 pmt pattern，用**重心法**重建出每个时间切片的位置中心。
  - 最终将所有时间切片的中心连接起来，画出**三维径迹**。

## 10. 缓存管理与数据溯源

- 预处理中间数据（如匹配后的事件结构、聚类 peak 结构、特征结果）可缓存至 `/mnt/data/tmp/muon_analysis/`。
- 缓存文件以 `run_id` + 处理参数的哈希值命名，确保同一条件下的结果一致，避免重复计算。
- 提供命令行选项：
  - `--clear-cache`：清空 `/mnt/data/tmp/muon_analysis/` 下所有缓存。
  - `--show-cache`：列出缓存条目及其对应的原始数据标识，便于追踪来源。
- 缓存空间不足时给出警告，不自动清除。

## 11. 用户交互与配置

- 命令行接口清晰，支持指定多 `run_id`、参数配置文件、输出目录等。
- 运行过程中输出进度条或关键统计（总事件数、peak 数、通过筛选的 muon 事例数、径迹重建数）。
- 所有可调参数（含 PMT gain 数据库路径、聚类窗口、筛条件、dynode 滤波/放大倍数、时间切片宽度等）通过 YAML/JSON 配置文件管理。

## 12. 非功能性需求

- **性能**：利用 NumPy 向量化及可选多进程并行，高效处理大批量数据。
- **可维护性**：代码模块化，数据读取、匹配、聚类、可视化、特征分析、筛选、输出、位置重建、径迹重建等功能独立封装，便于复用。
- **可重复性**：输出 CSV 中附带处理参数版本与 gain 数据库标识；缓存哈希机制保证结果一致性。

## 13. 补充技术约束与偏好

- 编程语言（Python 3.10+）。
- 依赖库偏好：NumPy, SciPy, Matplotlib, PyYAML, pandas, h5py 等。
- 项目结构要求：推荐使用 `src/`、`scripts/`、`config/`、`output/` 等目录。
- PMT pattern（位置）导入与 COG 重建复用已有成熟脚本。
