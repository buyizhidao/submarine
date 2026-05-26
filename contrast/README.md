# Nautilus Mapping 当前结果对比报告

## 数据来源

- 本地结果文件：`data/results/mapping_outputs/link_to_cable_and_score_mapping_v4`
- 类别文件：`data/results/mapping_outputs/categories_map_updated_v4`
- RIPE traceroute：`data/intermediate/ripe_data/processed_output_*`
- 海缆参考表：`data/raw/submarine/processed/*.csv`
- Nautilus API：`POST /api/traceroute`、`GET /api/ip`、`GET /api/lines`

本报告只说明当前本地结果的结构健康度和与 Nautilus 在线 API 的一致性，不把 API 输出视为绝对真值。

## 第一层：本地结果结构与覆盖率

- 总 IP 跳数量：602981
- 有最终海缆候选的 IP 跳：340472
- 无最终海缆候选的 IP 跳：262509
- 覆盖率：56.46%
- 结构异常数量：0
- 未在当前海缆表中匹配到的候选出现次数：169616

| 类别 | 总数 | 有候选 | 无候选 | 覆盖率 |
|---|---:|---:|---:|---:|
| bg_oc | 297390 | 171740 | 125650 | 57.75% |
| bg_te | 305591 | 168732 | 136859 | 55.22% |

score 分布见 `output/layer1_score_buckets.csv`，候选数量分布见 `output/layer1_summary.json`。

高频候选海缆前 10：

| 海缆 | 出现 link 数 |
|---|---:|
| SeaMeWe-3 | 54112 |
| Atlantic Crossing-1 (AC-1) | 49443 |
| Concerto | 48782 |
| BT North Sea | 40356 |
| Tangerine | 34390 |
| Ulysses 2 | 34379 |
| Farland North | 34270 |
| Circe North | 33788 |
| EAC-C2C | 24856 |
| FLAG Atlantic-1 (FA-1) | 24337 |

## 第二层：Nautilus API 当前对比

- 请求抽样数量：5
- 找到可提交 traceroute 的样本：5
- 完成 API 对比的样本：5
- API 可提取候选海缆的样本：1
- 提取方式统计：none: 4, geometry_inferred: 1
- Top-1 一致率：0.00%
- Top-3 命中率：0.00%
- 任意候选交集率：0.00%
- Jaccard 平均值：0.0
- 本地空候选但 API 有候选：1
- 本地有候选但 API 空候选：4

逐条对比见 `output/layer2_link_comparison.csv`，API 原始响应缓存见 `output/api_cache/`。

## 解释口径

如果 API 返回中能直接匹配到海缆名称或 ID，记为 `direct_name`。如果 API 只返回线路几何坐标，则将线段端点匹配到 75km 内的本地登陆点，并取两端登陆点共同连接的海缆，记为 `geometry_inferred`。几何反推是弱证据，不能与直接海缆名等价。

因此第二层指标应称为“与 Nautilus 在线 API 的一致性”，不是严格准确率。严格准确率仍需要人工黄金集或独立事件/运营商证据支持。
