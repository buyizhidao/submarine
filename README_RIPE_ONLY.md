# 仅使用 RIPE 数据的 Nautilus Mapping

该目录包含一个轻量级的 Nautilus 复现流程：使用 RIPE Atlas traceroutes、DB-IP/MaxMind 兼容的 GeoIP，不做 SoL 验证，也不进行 IP-to-AS/ASRank 所有者评分。

在 `mapping/code` 下运行命令。

## 环境

原始 `requirements.txt` 从 Nautilus 复制而来，固定了过旧版本，无法在 Python 3.12 上安装。请改用兼容的轻量版文件：

```powershell
python -m pip install -r ..\requirements-lite.txt
```

## 已准备的数据

DB-IP 数据库放置在：

```text
mapping/data/raw/location_data/GeoLite2-City.mmdb
```

首次运行使用 Nautilus 原始的海底光缆 pickle 文件，路径为：

```text
mapping/data/raw/submarine_data
```

IPUMSI 兼容的国家边界 shapefile 由以下脚本生成：

```powershell
python scripts\prepare_ipumsi_boundaries.py
```

旧的 IPUMSI zip URL 当前返回 404，因此脚本会回退到官方 IPUMS ArcGIS FeatureServer，并写入：

```text
../data/raw/IPUMSI_world_release2020/world_countries_2020.shp
```

## 流程

获取并处理 RIPE Atlas traceroutes：

```powershell
python scripts\fetch_ripe_traceroutes.py --start "2026-05-01 00:00" --end "2026-05-02 00:00" --ip-version 4 --measurements 5051 5151 --chunk-hours 0.5
```

RIPE 下载脚本默认启用断点继续。它会在 `../data/intermediate/ripe_data` 下写入
`ripe_resume_state_*` 和 `ripe_resume_checkpoint_*`；使用相同参数重新运行时，
会从下一个未完成分片继续。使用 `--no-resume` 可以忽略已保存状态并从头重建。

RIPE 获取命令的参数没有变化。当前脚本会在内部对 `--measurements` 中的测量 ID
使用最多 2 个线程并发处理，例如 `5051` 和 `5151` 会同时运行；不需要额外添加参数。
普通 RIPE-only 路径会流式处理 traceroute，并按 chunk 保存较小的
`ripe_chunk_links_*` 分片，最终仍写出原来的 `uniq_ip_dict_*` 文件供后续 mapping 使用。

在 mapping 过程中自动生成 `links_v4` 和 `all_ips_v4`，或通过 `utils.traceroute_utils.load_all_links_and_ips_data(source_mode="ripe_only")` 显式生成。

在 `all_ips_v4` 存在后生成 GeoIP 输出：

```powershell
python scripts\generate_geoip_locations.py --ip-version 4
```

运行 mode=0 映射：

```powershell
python scripts\run_mapping_mode0.py --ip-version 4
```

`run_mapping_mode0.py` 会自动在 `logs` 目录写入运行日志，同时仍然把输出显示在终端。
日志文件名形如：

```text
../logs/run_mapping_mode0_v4_20260522_153000.log
```

映射阶段默认启用断点继续。程序会优先复用已经完整生成且条数匹配的类别输出文件，
例如 `../data/intermediate/mapping_outputs/cable_mapping_bg_oc_v4`。如果类别尚未完整完成，
程序会使用 `../data/intermediate/mapping_outputs/checkpoints/` 下的分片 checkpoint，只重新计算缺失
或不完整的分片。最终仍会写出原来的标准结果文件，后续 merge 和 final mapping
不需要改命令。

常用参数含义：

- `--ip-version`：选择处理 IPv4 或 IPv6，只能是 `4` 或 `6`，默认 `4`。
- `--mmdb-file`：GeoIP 数据库路径，默认 `../data/raw/location_data/GeoLite2-City.mmdb`。
- `--skip-geoip`：跳过 GeoIP 生成，直接使用已经存在的 `maxmind_location_output_v*_default`。
- `--max-links`：烟雾测试参数，限制每个类别最多处理多少条 link。正式运行不要使用它。
- `--no-resume`：关闭断点继续，忽略已完成类别文件和 checkpoint 分片，重新计算映射阶段。
- `--checkpoint-links`：每个 checkpoint 分片包含的 link 数量，默认 `50000`。
- `--mapping-workers`：mapping 阶段用于处理 checkpoint 分片的 worker 进程数，默认 `1`，表示保持串行执行；设置为大于 `1` 时启用多进程并行。
- `--progress-interval`：终端和日志中每处理多少条 link 输出一次进度，默认 `5000`。
- `--log-dir`：运行日志目录，默认 `../logs`。
- `--log-level`：日志级别，默认 `INFO`。可选值包括 `DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。
- `--keep-checkpoints`：保留 checkpoint 分片文件。默认不加该参数时，如果完整类别输出文件 `cable_mapping_*_v*` 已经生成并验证通过，程序会自动删除对应 `data/intermediate/mapping_outputs/checkpoints/<save_file>/` 目录下的 `part_*` 分片文件；如果该 checkpoint 目录清空，则同时删除这个空目录。如果加上该参数，则不自动清理 checkpoint。

日志会同时输出到终端和 `../logs/` 下的文件，格式为：

```text
时间 | 级别 | 脚本名 | 模块:函数:行号 | 消息
```

以下直接运行的脚本也支持 `--log-dir` 和 `--log-level`：

```text
scripts/fetch_ripe_traceroutes.py
scripts/generate_geoip_locations.py
scripts/prepare_ipumsi_boundaries.py
scripts/convert_submarine_processed_to_nautilus_pickles.py
```

例如，复用已有 GeoIP 并按默认分片继续运行：

```powershell
python scripts\run_mapping_mode0.py --ip-version 4 --skip-geoip
```

如果希望更频繁保存 checkpoint，可以调小分片大小：

```powershell
python scripts\run_mapping_mode0.py --ip-version 4 --skip-geoip --checkpoint-links 10000
```

如果希望 mapping 阶段并行处理 checkpoint 分片，可以设置 worker 数：

```powershell
python scripts\run_mapping_mode0.py --ip-version 4 --skip-geoip --mapping-workers 4
```

并行模式仍使用原来的 checkpoint 文件和最终输出文件名。Windows 下每个 worker
都会加载一份较大的 mapping 数据，建议先从 `--mapping-workers 2` 或 `4` 开始，
根据内存占用再调整。默认不加该参数时行为不变。

做烟雾测试时可限制每类数量：

```powershell
python scripts\run_mapping_mode0.py --ip-version 4 --max-links 100
```

注意：`--max-links` 会写入与正式运行相同的输出文件名，仅用于测试流程是否能跑通。
正式运行前请确认没有把测试输出当作完整结果继续使用。

## 新海底光缆数据转换

位于 `mapping/data/raw/submarine/processed` 的新处理 CSV 可在之后转换：

```powershell
python scripts\convert_submarine_processed_to_nautilus_pickles.py --processed-dir ..\data\raw\submarine\processed --output-dir ..\data\raw\submarine_data_new
```

在仅 RIPE 流程能正常跑通原始 Nautilus 海底光缆 pickles 之前，不要覆盖 `../data/raw/submarine_data`。
