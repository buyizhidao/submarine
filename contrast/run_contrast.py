import argparse
import csv
import json
import os
import pickle
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

CONTRAST_DIR = Path(__file__).resolve().parent
MAPPING_ROOT = CONTRAST_DIR.parent
CODE_DIR = MAPPING_ROOT / 'code'
sys.path.insert(0, str(CODE_DIR))

from contrast_metrics import (  # noqa: E402
	candidate_names,
	candidate_scores,
	compare_candidates,
	extract_api_candidates,
	load_submarine_reference,
	mapping_has_candidates,
	score_bucket,
	summarize_layer1,
	top_score,
	write_csv,
	write_json,
)
from nautilus_api_client import NautilusApiClient  # noqa: E402
from traceroute.ripe_traceroute_utils import get_ripe_hops  # noqa: E402


OUTPUT_DIR = CONTRAST_DIR / 'output'
API_CACHE_DIR = OUTPUT_DIR / 'api_cache'
MAPPING_FILE = MAPPING_ROOT / 'data' / 'results' / 'mapping_outputs' / 'link_to_cable_and_score_mapping_v4'
CATEGORIES_FILE = MAPPING_ROOT / 'data' / 'results' / 'mapping_outputs' / 'categories_map_updated_v4'
SUBMARINE_PROCESSED_DIR = MAPPING_ROOT / 'data' / 'raw' / 'submarine' / 'processed'
RIPE_DATA_DIR = MAPPING_ROOT / 'data' / 'intermediate' / 'ripe_data'


def load_pickle(path):
	with Path(path).open('rb') as fp:
		return pickle.load(fp)


def link_to_text(link):
	return f'{link[0]} -> {link[1]}'


def link_to_id(link):
	return f'{link[0]}__{link[1]}'


def parse_link_id(value):
	left, right = value.split('__', 1)
	return left, right


def ensure_output_dirs():
	OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
	API_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def sample_links(mapping, sample_size, seed):
	random.seed(seed)
	groups = defaultdict(list)
	for link, value in mapping.items():
		candidates = candidate_names(value)
		if not candidates:
			candidate_state = 'empty'
		elif len(candidates) == 1:
			candidate_state = 'single'
		else:
			candidate_state = 'multi'
		key = (value[-1], candidate_state, score_bucket(top_score(value)))
		groups[key].append((link, value))

	for values in groups.values():
		random.shuffle(values)

	selected = []
	group_keys = sorted(groups.keys())
	while len(selected) < sample_size and group_keys:
		next_keys = []
		for key in group_keys:
			if groups[key] and len(selected) < sample_size:
				selected.append(groups[key].pop())
			if groups[key]:
				next_keys.append(key)
		group_keys = next_keys

	rows = []
	for link, value in selected:
		rows.append({
			'link_id': link_to_id(link),
			'ip1': link[0],
			'ip2': link[1],
			'category': value[-1],
			'candidate_count': len(candidate_names(value)),
			'top_score': top_score(value),
			'score_bucket': score_bucket(top_score(value)),
			'local_candidates': '; '.join(candidate_names(value)),
			'local_scores': '; '.join(str(round(score, 6)) for score in candidate_scores(value)),
		})
	return rows


def sample_rows(rows, sample_size, seed):
	random.seed(seed)
	groups = defaultdict(list)
	for row in rows:
		key = (row['category'], row['candidate_state'], row['score_bucket'])
		groups[key].append(row)

	for values in groups.values():
		random.shuffle(values)

	selected = []
	group_keys = sorted(groups.keys())
	while len(selected) < sample_size and group_keys:
		next_keys = []
		for key in group_keys:
			if groups[key] and len(selected) < sample_size:
				selected.append(groups[key].pop())
			if groups[key]:
				next_keys.append(key)
		group_keys = next_keys
	return selected


def trace_to_text(trace):
	hops = trace.hops
	dst_ip = None
	if 256 in hops and hops[256]:
		dst_ip = hops[256][0].ip_address
	if dst_ip is None:
		last_key = sorted(hops.keys())[-1]
		dst_ip = hops[last_key][0].ip_address

	lines = [f'traceroute to {dst_ip} ({dst_ip}), 30 hops max, 60 byte packets']
	for hop_num in sorted(hops.keys()):
		if hop_num == 0:
			continue
		entries = hops[hop_num]
		if not entries:
			continue
		parts = []
		seen = set()
		for entry in entries:
			key = (entry.ip_address, entry.rtt)
			if key in seen:
				continue
			seen.add(key)
			if entry.ip_address == '*':
				parts.append('*')
			else:
				parts.append(f'{entry.ip_address} {entry.rtt} ms')
		if parts:
			lines.append(f'{hop_num:2d}  ' + '  '.join(parts))
	return '\n'.join(lines)


def find_traceroutes_for_samples(sample_rows, max_files=None):
	needed = {}
	for row in sample_rows:
		link = (row['ip1'], row['ip2'])
		needed[link] = row['link_id']
		needed[(link[1], link[0])] = row['link_id']

	found = {}
	files = sorted(RIPE_DATA_DIR.glob('processed_output_*'), key=lambda path: path.stat().st_mtime)
	if max_files:
		files = files[:max_files]

	for file_path in files:
		if len(found) >= len(sample_rows):
			break
		with file_path.open('rb') as fp:
			traces = pickle.load(fp)
		for trace in traces:
			if len(found) >= len(sample_rows):
				break
			try:
				hops, _, _ = get_ripe_hops(trace, True)
			except Exception:
				continue
			trace_links = {hop[0] for hop in hops}
			overlap = trace_links & set(needed.keys())
			for link in overlap:
				sample_id = needed[link]
				if sample_id not in found:
					found[sample_id] = {
						'source_file': file_path.name,
						'matched_link': link_to_id(link),
						'traceroute_text': trace_to_text(trace),
					}
	return found


def collect_trace_backed_candidates(mapping, pool_limit, max_files=None):
	rows = []
	trace_matches = {}
	seen = set()
	files = sorted(RIPE_DATA_DIR.glob('processed_output_*'), key=lambda path: path.stat().st_mtime)
	if max_files:
		files = files[:max_files]

	for file_path in files:
		if len(rows) >= pool_limit:
			break
		with file_path.open('rb') as fp:
			traces = pickle.load(fp)
		for trace in traces:
			if len(rows) >= pool_limit:
				break
			try:
				hops, _, _ = get_ripe_hops(trace, True)
			except Exception:
				continue
			trace_text = None
			for hop in hops:
				link = hop[0]
				if link in mapping:
					canonical = link
				elif (link[1], link[0]) in mapping:
					canonical = (link[1], link[0])
				else:
					continue
				if canonical in seen:
					continue
				seen.add(canonical)
				value = mapping[canonical]
				candidates = candidate_names(value)
				if not candidates:
					candidate_state = 'empty'
				elif len(candidates) == 1:
					candidate_state = 'single'
				else:
					candidate_state = 'multi'
				if trace_text is None:
					trace_text = trace_to_text(trace)
				link_id = link_to_id(canonical)
				rows.append({
					'link_id': link_id,
					'ip1': canonical[0],
					'ip2': canonical[1],
					'category': value[-1],
					'candidate_state': candidate_state,
					'candidate_count': len(candidates),
					'top_score': top_score(value),
					'score_bucket': score_bucket(top_score(value)),
					'local_candidates': '; '.join(candidates),
					'local_scores': '; '.join(str(round(score, 6)) for score in candidate_scores(value)),
				})
				trace_matches[link_id] = {
					'source_file': file_path.name,
					'matched_link': link_to_id(link),
					'traceroute_text': trace_text,
				}
	return rows, trace_matches


def combine_api_payload(api_result):
	payload = {}
	for key in ['submit', 'ip', 'lines']:
		record = api_result.get(key, {})
		payload[key] = record.get('json')
	return payload


def run_layer1(mapping, categories_map, reference):
	layer1 = summarize_layer1(mapping, categories_map, reference['known_cable_names'])
	write_json(OUTPUT_DIR / 'layer1_summary.json', layer1['summary'])
	write_csv(
		OUTPUT_DIR / 'layer1_category_stats.csv',
		layer1['category_rows'],
		['category', 'total_links', 'mapped_links', 'empty_links', 'mapped_rate', 'category_map_links'],
	)
	write_csv(OUTPUT_DIR / 'layer1_score_buckets.csv', layer1['score_rows'], ['score_bucket', 'links'])
	write_csv(OUTPUT_DIR / 'layer1_top_cables.csv', layer1['top_cable_rows'], ['cable', 'links'])
	write_json(OUTPUT_DIR / 'layer1_structure_errors.json', layer1['structure_errors'])
	write_csv(OUTPUT_DIR / 'layer1_unknown_cables.csv', layer1['unknown_cable_rows'], ['cable', 'count'])
	return layer1


def run_layer2(args, mapping, reference):
	candidate_pool, trace_matches_all = collect_trace_backed_candidates(
		mapping,
		max(args.sample_size * 20, args.sample_size),
		args.max_ripe_files,
	)
	samples = sample_rows(candidate_pool, args.sample_size, args.seed)
	selected_ids = {row['link_id'] for row in samples}
	trace_matches = {
		link_id: trace_info
		for link_id, trace_info in trace_matches_all.items()
		if link_id in selected_ids
	}
	write_csv(
		OUTPUT_DIR / 'sample_links.csv',
		samples,
		['link_id', 'ip1', 'ip2', 'category', 'candidate_count', 'top_score', 'score_bucket', 'local_candidates', 'local_scores'],
	)
	write_json(OUTPUT_DIR / 'sample_traceroute_matches.json', {
		key: {
			'source_file': value['source_file'],
			'matched_link': value['matched_link'],
		}
		for key, value in trace_matches.items()
	})

	api_rows = []
	comparison_rows = []
	if args.no_api:
		return {
			'samples': samples,
			'trace_matches': trace_matches,
			'api_rows': api_rows,
			'comparison_rows': comparison_rows,
			'summary': {'api_skipped': True},
		}

	client = NautilusApiClient(
		args.api_base,
		API_CACHE_DIR,
		rate_limit_seconds=args.rate_limit_seconds,
		timeout=args.timeout,
		retries=args.retries,
	)

	sample_by_id = {row['link_id']: row for row in samples}
	for sample_id, trace_info in trace_matches.items():
		api_result = client.run_for_traceroute(sample_id, trace_info['traceroute_text'])
		api_payload = combine_api_payload(api_result)
		api_candidates, extraction_method = extract_api_candidates(api_payload, reference)
		sample_row = sample_by_id[sample_id]
		local_link = parse_link_id(sample_id)
		local_candidates = candidate_names(mapping[local_link])
		metrics = compare_candidates(local_candidates, api_candidates)

		api_rows.append({
			'link_id': sample_id,
			'extraction_method': extraction_method,
			'api_candidate_count': len(api_candidates),
			'api_candidates': '; '.join(api_candidates),
			'submit_status': api_result['submit'].get('status_code'),
			'ip_status': api_result['ip'].get('status_code'),
			'lines_status': api_result['lines'].get('status_code'),
			'source_file': trace_info['source_file'],
		})

		comparison_rows.append({
			'link_id': sample_id,
			'category': sample_row['category'],
			'score_bucket': sample_row['score_bucket'],
			'local_candidate_count': metrics['local_candidate_count'],
			'api_candidate_count': metrics['api_candidate_count'],
			'extraction_method': extraction_method,
			'top1_agreement': metrics['top1_agreement'],
			'top3_hit': metrics['top3_hit'],
			'any_overlap': metrics['any_overlap'],
			'overlap_count': metrics['overlap_count'],
			'jaccard': metrics['jaccard'],
			'mrr': metrics['mrr'],
			'local_candidates': '; '.join(local_candidates),
			'api_candidates': '; '.join(api_candidates),
		})

	write_csv(
		OUTPUT_DIR / 'api_extracted.csv',
		api_rows,
		['link_id', 'extraction_method', 'api_candidate_count', 'api_candidates', 'submit_status', 'ip_status', 'lines_status', 'source_file'],
	)
	write_csv(
		OUTPUT_DIR / 'layer2_link_comparison.csv',
		comparison_rows,
		[
			'link_id', 'category', 'score_bucket', 'local_candidate_count', 'api_candidate_count',
			'extraction_method', 'top1_agreement', 'top3_hit', 'any_overlap', 'overlap_count',
			'jaccard', 'mrr', 'local_candidates', 'api_candidates',
		],
	)

	summary = summarize_layer2(samples, trace_matches, comparison_rows)
	write_json(OUTPUT_DIR / 'layer2_summary.json', summary)
	return {
		'samples': samples,
		'trace_matches': trace_matches,
		'api_rows': api_rows,
		'comparison_rows': comparison_rows,
		'summary': summary,
	}


def summarize_layer2(samples, trace_matches, comparison_rows):
	method_counter = Counter(row['extraction_method'] for row in comparison_rows)
	usable = [row for row in comparison_rows if row['api_candidate_count'] > 0]

	def rate(rows, key):
		if not rows:
			return None
		return round(sum(1 for row in rows if str(row[key]).lower() == 'true') / len(rows), 6)

	jaccards = [float(row['jaccard']) for row in usable if row['jaccard'] not in [None, '']]
	return {
		'requested_samples': len(samples),
		'traceroute_matched_samples': len(trace_matches),
		'api_compared_samples': len(comparison_rows),
		'api_samples_with_candidates': len(usable),
		'extraction_methods': dict(method_counter),
		'top1_agreement_rate': rate(usable, 'top1_agreement'),
		'top3_hit_rate': rate(usable, 'top3_hit'),
		'any_overlap_rate': rate(usable, 'any_overlap'),
		'jaccard_avg': round(sum(jaccards) / len(jaccards), 6) if jaccards else None,
		'local_empty_api_has_candidates': sum(
			1 for row in comparison_rows
			if row['local_candidate_count'] == 0 and row['api_candidate_count'] > 0
		),
		'local_has_candidates_api_empty': sum(
			1 for row in comparison_rows
			if row['local_candidate_count'] > 0 and row['api_candidate_count'] == 0
		),
	}


def render_readme(layer1, layer2):
	summary = layer1['summary']
	layer2_summary = layer2.get('summary', {})
	category_lines = []
	for row in layer1['category_rows']:
		category_lines.append(
			f"| {row['category']} | {row['total_links']} | {row['mapped_links']} | "
			f"{row['empty_links']} | {row['mapped_rate']:.2%} |"
		)

	top_cables = layer1['top_cable_rows'][:10]
	top_cable_lines = [f"| {row['cable']} | {row['links']} |" for row in top_cables]

	methods = layer2_summary.get('extraction_methods', {})
	method_text = ', '.join(f'{key}: {value}' for key, value in methods.items()) if methods else '无'

	content = f"""# Nautilus Mapping 当前结果对比报告

## 数据来源

- 本地结果文件：`data/results/mapping_outputs/link_to_cable_and_score_mapping_v4`
- 类别文件：`data/results/mapping_outputs/categories_map_updated_v4`
- RIPE traceroute：`data/intermediate/ripe_data/processed_output_*`
- 海缆参考表：`data/raw/submarine/processed/*.csv`
- Nautilus API：`POST /api/traceroute`、`GET /api/ip`、`GET /api/lines`

本报告只说明当前本地结果的结构健康度和与 Nautilus 在线 API 的一致性，不把 API 输出视为绝对真值。

## 第一层：本地结果结构与覆盖率

- 总 IP 跳数量：{summary['total_links']}
- 有最终海缆候选的 IP 跳：{summary['mapped_links']}
- 无最终海缆候选的 IP 跳：{summary['empty_links']}
- 覆盖率：{summary['mapped_rate']:.2%}
- 结构异常数量：{summary['structure_error_count']}
- 未在当前海缆表中匹配到的候选出现次数：{summary['unknown_cable_count']}

| 类别 | 总数 | 有候选 | 无候选 | 覆盖率 |
|---|---:|---:|---:|---:|
{chr(10).join(category_lines)}

score 分布见 `output/layer1_score_buckets.csv`，候选数量分布见 `output/layer1_summary.json`。

高频候选海缆前 10：

| 海缆 | 出现 link 数 |
|---|---:|
{chr(10).join(top_cable_lines)}

## 第二层：Nautilus API 当前对比

- 请求抽样数量：{layer2_summary.get('requested_samples', 0)}
- 找到可提交 traceroute 的样本：{layer2_summary.get('traceroute_matched_samples', 0)}
- 完成 API 对比的样本：{layer2_summary.get('api_compared_samples', 0)}
- API 可提取候选海缆的样本：{layer2_summary.get('api_samples_with_candidates', 0)}
- 提取方式统计：{method_text}
- Top-1 一致率：{_fmt_rate(layer2_summary.get('top1_agreement_rate'))}
- Top-3 命中率：{_fmt_rate(layer2_summary.get('top3_hit_rate'))}
- 任意候选交集率：{_fmt_rate(layer2_summary.get('any_overlap_rate'))}
- Jaccard 平均值：{_fmt_number(layer2_summary.get('jaccard_avg'))}
- 本地空候选但 API 有候选：{layer2_summary.get('local_empty_api_has_candidates', 0)}
- 本地有候选但 API 空候选：{layer2_summary.get('local_has_candidates_api_empty', 0)}

逐条对比见 `output/layer2_link_comparison.csv`，API 原始响应缓存见 `output/api_cache/`。

## 解释口径

如果 API 返回中能直接匹配到海缆名称或 ID，记为 `direct_name`。如果 API 只返回线路几何坐标，则将线段端点匹配到 75km 内的本地登陆点，并取两端登陆点共同连接的海缆，记为 `geometry_inferred`。几何反推是弱证据，不能与直接海缆名等价。

因此第二层指标应称为“与 Nautilus 在线 API 的一致性”，不是严格准确率。严格准确率仍需要人工黄金集或独立事件/运营商证据支持。
"""
	(CONTRAST_DIR / 'README.md').write_text(content, encoding='utf-8')


def _fmt_rate(value):
	if value is None:
		return '无可用样本'
	return f'{value:.2%}'


def _fmt_number(value):
	if value is None:
		return '无'
	return str(value)


def parse_args():
	parser = argparse.ArgumentParser(description='Run local and Nautilus API contrast checks.')
	parser.add_argument('--layer', choices=['1', '2', 'all'], default='all')
	parser.add_argument('--sample-size', type=int, default=300)
	parser.add_argument('--seed', type=int, default=20260526)
	parser.add_argument('--api-base', default='https://nautilus.ics.uci.edu')
	parser.add_argument('--rate-limit-seconds', type=float, default=1.0)
	parser.add_argument('--timeout', type=int, default=60)
	parser.add_argument('--retries', type=int, default=3)
	parser.add_argument('--no-api', action='store_true')
	parser.add_argument('--max-ripe-files', type=int, default=None)
	return parser.parse_args()


def main():
	args = parse_args()
	ensure_output_dirs()

	mapping = load_pickle(MAPPING_FILE)
	categories_map = load_pickle(CATEGORIES_FILE)
	reference = load_submarine_reference(SUBMARINE_PROCESSED_DIR)

	layer1 = run_layer1(mapping, categories_map, reference)
	layer2 = {'summary': {'api_skipped': True}}
	if args.layer in ['2', 'all']:
		layer2 = run_layer2(args, mapping, reference)

	render_readme(layer1, layer2)
	print(f'Contrast report written to: {CONTRAST_DIR / "README.md"}')


if __name__ == '__main__':
	main()
