## 生成 Nautilus 映射

Nautilus 映射分为 (i) 预处理 和 (ii) 实际映射阶段。之所以这样划分，是因为测量规模很大（即百万级），需要保证效率。

注意：所有文件都需要在代码库根目录（即 nautilus/code/ 目录）下运行，以确保能够正确访问所有中间文件表示。

## 预处理步骤

### 生成 traceroute

Nautilus 的 traceroute 来自两类来源：(i) RIPE Atlas — IPv4 使用 5051 和 5151，IPv6 使用 6052 和 6152；(ii) CAIDA — IPv4 和 IPv6 分别进行 /24 与 /48 前缀探测。

#### RIPE Atlas traceroute 生成

在给定时间范围内生成 traceroute，可使用如下代码段。以下示例为 2022 年 3 月 15 日至 29 日、测量 ID 为 5151 的代码。相关函数位于“traceroute/ripe_traceroute_utils.py”文件中。

```
start_time = datatime(2022, 3, 15, 0)
end_time = datetime(2022, 3, 29, 0)
ripe_process_traceroutes(start_time, end_time, '5151', 4, False)
```

在上述函数中，4 表示 IP 版本；用于初始 traceroute 收集时，最后一个参数应设为 False。该操作的结果将保存为文件“../data/intermediate/ripe_data/uniq_ip_dict_5151_…..”。

注意：上述操作会生成多个文件，但实际需要的是最终生成的文件，通常文件名末尾包含“`<date>`_count_”。例如，上述操作最终会生成“uniq_ip_dict_5151_all_links_v4_min_all_latencies_only_03_29_2022_00_00_count_28”，该文件将用于后续处理。

#### CAIDA traceroute 生成

从 CAIDA 生成 traceroute 时，不使用时间范围，而是使用对应的 cycle id。例如 2022 年 3 月 13-23 日对应的 cycle id 为 1647。该示例的代码如下。相关函数位于“traceroute/caida_traceroute_utils.py”文件中。

`caida_process_traceroutes(2022, 3, 1647, 4, 1000, False) `

其中 1647 为 cycle id，2022 与 3 为该 cycle 的年份与月份，4 表示 IP 版本，最后两个参数在初始 traceroute 生成阶段可使用默认值。

注意：运行上述代码需要安装 CAIDA 的“scamper”工具，用于处理从 CAIDA 服务器下载的 warts 文件。最终生成的文件位于“../data/intermediate/caida_data/uniq_ip_dict_caida_all_links_v4_min_all_latencies_only_….”。

注意：使用 CAIDA 进行 /24 探测（IPv4）需要权限，代码会提示输入用户名与密码以执行并处理 CAIDA traceroute。IPv6 数据为公开数据，若提供测量 ID，Nautilus 会自动拉取并处理所需 traceroute。

### 生成全部唯一 IP 与链路

当 RIPE 与 CAIDA 的 traceroute 生成完成后，需要获取所有相关的 IP 端点与链路。代码片段如下，函数位于“utils/traceroute_utils.py”文件中。

`load_all_links_and_ips_data(ip_version=4)`

该操作会在“../data/intermediate/mapping_outputs”目录下生成“all_ips_v4”和“links_v4”，分别对应唯一 IP 列表与链路列表。

### 生成地理定位结果

#### RIPE 地理定位

运行地理定位脚本前，需要从 RIPE ftp 服务器下载必要的 RIPE 地理定位文件，并放入“../data/raw/location_data”目录。代码片段如下，函数细节位于“location/ripe_geolocation_utils.py”文件中。

```
links, ips = load_all_links_and_ips_data (ip_version=4)
generate_location_for_list_of_ips_ripe(ips, ip_version=4)
```

该代码片段会在“../data/raw/location_data”目录下生成 RIPE 地理定位结果“ripe_location_output_v4_default”。

#### CAIDA 地理定位

对于 CAIDA，需要从 CAIDA Ark 平台下载 midar.iff 与 midar.iff.nodes.geo 文件，并放入“../data/raw/location_data”目录。获取 CAIDA 地理定位的代码如下，函数细节位于“location/caida_geolocation_utils.py”文件中。

```
links, ips = load_all_links_and_ips_data (ip_version=4)
generate_location_for_list_of_ips(ips)
```

该代码片段会在“../data/raw/location_data”目录下生成 CAIDA 地理定位结果“caida_location_output_default”。

#### Maxmind 地理定位

要运行 Maxmind 地理定位，需要从 Maxmind 网站下载 Geolite-city.mmdb 文件，并放入“../data/raw/location_data”目录。代码如下，函数细节位于“location/maxmind_geolocation_utils.py”文件中。

```
links, ips = load_all_links_and_ips_data (ip_version=4)
generate_locations_for_list_of_ips(ips, ip_version=4)
```

该代码片段会在“../data/raw/location_data”目录下生成 Maxmind 地理定位结果“maxmind_location_output_v4_default”。

#### 其他地理定位

其余地理定位依赖聚合网站。可使用以下代码获取相应 IP 位置，相关函数位于“location/ipgeolocation_utils.py”文件中。

```
args = {}
ip_version = 4
args['chromedriver_location'] = input('Enter chromedriver full path: ')
links, ips = load_all_links_and_ips_data (ip_version=4)
generate_location_for_list_of_ips (list_of_ips, in_chunks=False, args=args)
common_merge_operation('../data/raw/location_data/iplocation_files', 2, [], ['ipgeolocation_file_'], True, f’iplocation_location_output_v{ip_version}_default') % This operation is from the 'utils/merge_utils.py' file
```

初始生成的文件位于“../data/raw/location_data/iplocation_files”目录。

### SoL 校验

完成所有地理定位计算后，需要进行 SoL 校验。对于 IPv4，需要执行如下代码片段。

```
% First generating the probe to coordinate mappings which are essential for SoL validation
% For RIPE, the following code snippet can be used (found in ‘traceroute/ripe_probe_location_info.py’ file)
load_probe_location_result() 

% For CAIDA, use the following (found in ‘traceroute/caida_probe_location_info.py’ file)
load_probe_to_coordinate_map()

% Re-running traceroutes to perform SoL validation
ripe_process_traceroutes(start_time, end_time, '5151', 4, True)
ripe_process_traceroutes(start_time, end_time, '5051', 4, True)
caida_process_traceroutes(2022, 3, 1647, 4, 1000, True)
common_merge_operation('../data/raw/location_data', 0, [], ['validated_ip_locations'], True, 'all_validated_ip_location_v4') % This operation is from the 'utils/merge_utils.py' file
```

SoL 校验后的地理定位信息会保存到“../data/raw/location_data/ all_validated_ip_location_v4”。

注意：与初始 traceroute 生成步骤的主要区别在于 ripe_process_traceroutes 与 caida_process_traceroutes 的最后一个参数需设为 True，以触发 SoL 校验。若在地理定位结果生成之前将该参数设为 True，会出现错误。

### 聚类

我们使用 DBSCAN 对校验后的地理定位结果进行聚类。注意：论文中提到的聚类阈值为 20 km，但论文的最终结果使用了 100 km 阈值，与代码一致。

### IP 到 AS 映射

生成 IP 到 AS 映射可使用 ip_to_as 目录中的文件。IPv4 的示例代码如下。

```
links, ips = load_all_links_and_ips_data (ip_version=4)

% For RPKI queries use the following (function details in 'ip_to_as/whois_rpki_utils.py')
args = {}
args['chromedriver_location'] = input('Enter chromedriver full path: ')
generate_ip2as_for_list_of_ips(ip_version=4, ips, args=args, in_chunks=False)

% For RADB querying use (function details in 'ip_to_as/whois_radb_utils.py')
args = {}
args['whois_cmd_location'] = '/usr/bin/whois'
generate_ip2as_for_list_of_ips(ip_version=4, ips, args=args, in_chunks=False)

% For Cymru whois queries, use (function details in 'ip_to_as/cymru_whois_utils.py')
generate_ip2as_for_list_of_ips(ips, 4)
```

所有生成的 IP 到 AS 映射会保存到“../data/intermediate/ip2as_data”目录下。

注意：此外，IPv4 还需要从 CAIDA ITDK 下载相应的 CAIDA IP 到 AS 映射，并保存为 '../data/intermediate/ip2as_data/caida_whois_output_v4_default'。

## Nautilus 映射

当所有先决信息都生成后，即可进行实际的 Nautilus 映射。以下为映射的代码片段，与该阶段相关的文件位于 utils 目录（主要包括 'utils/common_utils.py'、'utils/geolocation_utils.py'、'utils/as_utils.py' 和 'utils/merge_utils.py'）。

```
mode = 1
ip_version = 4

% Generate an initial mapping for each category
generate_cable_mapping(mode=mode, ip_version=ip_version, sol_threshold=0.05)

% Generating a final mapping file for each category
common_merge_operation('../data/intermediate/mapping_outputs', 1, [], ['v4'], True, None)

% Merging the results for all categories and re-updating the categories map
generate_final_mapping(mode=mode, ip_version=ip_version, threshold=0.05)
regenerate_categories_map (mode=mode, ip_version=ip_version)
```

如果先前的预处理步骤未正确完成，运行上述代码片段时会显示错误信息，指出缺失的部分。除预处理步骤外，还需要完成以下一次性操作或下载：

(i) 从 IPUMSI 下载国家边界的 shape 文件（https://international.ipums.org/international/resources/gis/IPUMSI_world_release2020.zip），解压后的文件夹需保存到 stats 目录。
(ii) 使用以下命令执行 asrank.py 脚本：“python utils/asrank.py -v -a ../data/intermediate/asns.jsonl -o ../data/intermediate/organizations.jsonl -l ../data/intermediate/asnLinks.jsonl -u https://api.asrank.caida.org/v2/graphql”（此部分代码与数据来自 CAIDA ASRank）。

最终映射结果会在 'stats' 目录中生成：IPv4 为 'link_to_cable_and_score_mapping_sol_validated_v4'，IPv6 为 'link_to_cable_and_score_mapping_sol_validated_v6'。

# 与既有工作对比与验证

与既有工作对比及验证的相关文件分别位于 'experiments' 与 'validation' 目录中。

## 与既有工作对比

### iGDB

运行 iGDB 前，需要先从 https://github.com/standerson4/iGDB 下载代码库，并将两个文件（位于 experiments/iGDB/code）保存到 iGDB 的 code 目录中（结构与当前保存方式一致）。若与其默认地理定位结果对比，执行 'submarine_mapping.py'；若使用 Nautilus 的地理定位结果对比，执行 'submarine_mapping_with_nautilus_geolocation.py'。

### Criticality-SCN

与 SCN-Crit 对比时，使用 'experiments/scn_crit' 文件夹中的文件。我们已保存 SCN-Crit 论文中的结果为 'country_ip_sol_bundles.jsonl' 和 'country_ip_sol_bundles.jsonl.1'，并使用 '50_websites_mapping.py' 与 Nautilus 的映射结果进行对比。

注意：运行 50_websites_mapping.py 前，需要先执行 launch_ripe_traceroute.py 文件，该过程需要 RIPE credits 来进行测量，因此脚本运行时会提示输入 RIPE key。

## 验证

### 与历史海缆故障对比

'validation/failure_analysis.py' 文件包含一个示例（论文中的 Yemen 海缆故障）。该文件可修改以提供正确的结束日期、故障电缆及登陆点，从而计算故障发生前、期间与之后的链路数量。该程序当前会下载 5051 与 5151 测量中与每个场景结束日期前 2 天对应的 traceroute 数据。

注意：该文件默认每次都会自动下载与所提供日期对应的 RIPE traceroute。如果需要关闭（例如同一故障时间段的第 2 或第 3 次运行），可将自动 RIPE traceroute 下载与处理关闭，即把 get_ripe_data_for_given_end_date(date, True) 改为 get_ripe_data_for_given_end_date(date, False)。

### 定向 traceroute 测量

定向 traceroute 测量通过 'validation/loose_constraints_analysis.py' 文件完成。在执行该文件前，需要先执行 'validation/probe_search_and_initiate_traceroutes.py' 以生成相关 traceroute，随后由 'validation/loose_constraints_analysis.py' 进行分析。

注意：这些测量会消耗大量 RIPE credits，运行前请谨慎评估。

注意：定向 traceroute 测量同样依赖 RIPE credits，并会提示输入 RIPE key 以及自定义关键词（用于在测量完成后搜索）。

### 地理定位验证

为评估地理定位映射的准确性，Nautilus 以此前论文生成的地理定位真值数据为基准进行评估。为此，需要执行文件 'validation/geolocation_validation.py'。
