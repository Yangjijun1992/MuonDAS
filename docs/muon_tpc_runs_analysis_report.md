# Muon TPC Runs 批量分析结果报告

> 生成时间：2026-08-07 00:17:07
> 分析脚本：`scripts/run_batch.py`（每 3 个 run 一组并行、内存/磁盘保护、可续跑）
> 数据来源：`docs/tpc_runs.csv`（共 **50** 个 run_id，全部位于 `runtype = run6_Xe`）
> 配套文档：[需求](muon_dynode_analysis_requirements.md) / [实施计划](muon_dynode_analysis_implementation_plan.md) / [交付内容](muon_analysis_delivery.md)

## 1. 总体结果

| 指标 | 值 |
|---|---|
| 待分析 run 数 | 50 |
| 成功 | **47** |
| 失败 / **暂不分析** | **3**（已标记为暂缓，见下） |
| 通过所有筛选的候选事例总数（成功 run 合计） | **146** |
| 候选数为 0 的成功 run | 15 |
| 候选出现的通道集合 | ch9, ch10, ch11, ch12, ch13, ch14, ch15 |

> **暂缓分析**：此处 50 个 run 中，3 个读取失败的 run（**00211、00212、00213**）**暂时不再分析**，
> 仅在本报告中保留标记与原因记录，待后续需要时再补跑。

## 2. 每 run 详细结果

| run_id | 状态 | 候选数 | 出现通道(ch) | 输出文件数 |
|---|---|---|---|---|
| 00183 | OK | 11 | 9,11,12,13,14,15 | 10 |
| 00184 | OK | 2 | 13,15 | 10 |
| 00185 | OK | 2 | 9,14 | 10 |
| 00189 | OK | 4 | 9,13 | 10 |
| 00190 | OK | 16 | 9,10,11,12,13,14,15 | 10 |
| 00191 | OK | 2 | 15 | 10 |
| 00192 | OK | 10 | 9,13,14,15 | 10 |
| 00193 | OK | 0 | - | 2 |
| 00194 | OK | 3 | 9,15 | 10 |
| 00195 | OK | 4 | 9,13 | 10 |
| 00196 | OK | 7 | 11,12,13,15 | 10 |
| 00197 | OK | 0 | - | 2 |
| 00205 | OK | 0 | - | 2 |
| 00206 | OK | 1 | 13 | 10 |
| 00207 | OK | 0 | - | 2 |
| 00208 | OK | 6 | 9,11,13,15 | 10 |
| 00209 | OK | 1 | 9 | 10 |
| 00210 | OK | 3 | 9,14,15 | 10 |
| 00214 | OK | 5 | 9,13,14 | 10 |
| 00215 | OK | 0 | - | 2 |
| 00216 | OK | 4 | 9,13 | 10 |
| 00217 | OK | 0 | - | 2 |
| 00219 | OK | 4 | 9,12,15 | 10 |
| 00220 | OK | 0 | - | 2 |
| 00221 | OK | 10 | 11,12,13,14,15 | 10 |
| 00222 | OK | 0 | - | 2 |
| 00223 | OK | 1 | 10 | 10 |
| 00224 | OK | 0 | - | 2 |
| 00225 | OK | 2 | 15 | 10 |
| 00226 | OK | 6 | 9,13,15 | 10 |
| 00227 | OK | 1 | 9 | 10 |
| 00228 | OK | 0 | - | 2 |
| 00229 | OK | 0 | - | 2 |
| 00230 | OK | 11 | 9,11,12,14,15 | 10 |
| 00231 | OK | 0 | - | 2 |
| 00232 | OK | 3 | 9,11 | 10 |
| 00233 | OK | 1 | 15 | 10 |
| 00234 | OK | 0 | - | 2 |
| 00235 | OK | 5 | 9,15 | 10 |
| 00236 | OK | 2 | 9,15 | 10 |
| 00237 | OK | 6 | 11,13,14,15 | 10 |
| 00238 | OK | 1 | 9 | 10 |
| 00239 | OK | 4 | 9,14,15 | 10 |
| 00240 | OK | 0 | - | 2 |
| 00241 | OK | 4 | 9 | 10 |
| 00242 | OK | 0 | - | 2 |
| 00243 | OK | 4 | 9,13,15 | 10 |
| 00211 | **暂缓** | - | - | 0 |
| 00212 | **暂缓** | - | - | 0 |
| 00213 | **暂缓** | - | - | 0 |

## 3. 失败原因分析（已暂缓，暂不再分析）

> **当前决策**：以下 3 个 run **暂不分析**，仅保留失败原因记录；待后续需要时再补跑。

3 个 run（**00211, 00212, 00213**）均在数据读取阶段失败，报错形式如：

```
[run_id=00211] ERROR: read: Plugin 'records' failed: [Errno 2] No such file or directory: '/tmp/v1725_parts_*/.../records_part_*.dat'
[run_id=00212] ERROR: read: Plugin 'records' failed: [Errno 2] No such file or directory: '/tmp/v1725_parts_*/.../records_part_*.dat'
[run_id=00213] ERROR: read: Plugin 'records' failed: [Errno 2] No such file or directory: '/tmp/v1725_parts_*/.../records_part_*.dat'
```

原因：`waveform_analysis` 在读取 V1725 数据时会先在 `/tmp/v1725_parts_*/` 临时目录分块暂存解析后的记录。当每 3 个重载 run（约各 50M 事件 / 数十 GB）并行时，各 run 共享的 `/tmp` 暂存文件产生冲突/被清理，导致找不到暂存分块文件而读取失败。**规避建议**：对这几个 run 降并行度（组内 2 个或串行）后重跑。

其余成功 run 的耗时主要受限于：全量加载 + 时间匹配 + 特征/PE 计算的单线程/多线程 I/O，且在共享机器上受其他任务 I/O 竞争影响。

## 4. 输出产物（每 run 目录 `/tmp/mm_out<run_id>/`）

| 文件 | 说明 |
|---|---|
| `events_run_<id>.csv` | 候选事例级 CSV（含 anode/dynode_area_pe、seg_area_pe、event_length、channel、parameter_version、gain_db_version 等） |
| `waveforms_run_<id>.npz` | 候选波形片段（shape 约 `(N, 2, 100)`，阳极/打拿极，如有候选） |
| `compare_run_<id>.png` | 阳极-打拿极波形叠加对比图 |
| `hist_anode_area_pe/dynode_area_pe/seg_*/dt_ns_<id>.png` | 特征分布直方图 |
| `correlation_run_<id>.png` | anode vs dynode area 相关散点 |
| `segarea_len_run_<id>.png` | 段面积 vs 波形长度 2D 直方 |
| `run_<id>_metadata.json` | 运行元数据 |

## 5. 缓存内容

| 项 | 值 |
|---|---|
| 匹配缓存目录 | `/tmp/muon_analysis/` |
| 缓存文件数（`*_match.npy`） | **52** 个 |
| 缓存总大小 | **114 MB** |
| 命名规则 | `<run_id>__<参数哈希>_match.npy`（同一处理参数下结果一致，避免重复匹配） |
| 残留 staging 临时目录 | `/tmp/v1725_parts_*`（**32** 个，分析工具留下的临时分块文件） |

> 说明：缓存用于加速重跑（命中后跳过耗时的 `merge_asof` 时间匹配）；staging 临时目录为 `waveform_analysis` 分块暂存，可安全清理。

## 6. 运行配置（本次批量所用）

```yaml
# 每次并行组大小 / 内存保护阈值（scripts/run_batch.py 参数）
group_size: 3
min_free_gb: 60       # 可用内存低于此值则暂停等待
min_disk_gb: 20       # /tmp 磁盘余量低于此值则暂停
# 增益后端
gain_db: backend=pmtdata (按 run 查询；无条目时回退每通道最新 spe_gain)
# 默认筛选阈值（config/analysis.yaml）
filtering: asym_min=0.7, min_event_length=7000, min_seg_area_pe=20000
matching:  match_window_ns=[0,30], dynode_shift_ns=16, sample_interval_ns=4
features:  integral_window_mode=fixed, integral_start=20, integral_end=100
```

## 7. 复现命令

```bash
# 批量分析（已完成的 run 会自动跳过）
python scripts/run_batch.py --csv docs/tpc_runs.csv \
    --out-root /tmp/mm_out --group-size 3 --min-free-gb 60 \
    --data-root /mnt/data/TPC --gain-backend pmtdata
```

> **暂缓 run（00211/00212/00213）暂不补跑**。如需将来补跑，降并行度以规避 `/tmp` 暂存冲突：
>
> ```bash
> python scripts/run_batch.py 00211 00212 00213 \
>     --out-root /tmp/mm_out --group-size 1 --data-root /mnt/data/TPC
> ```

