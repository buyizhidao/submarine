import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path


SCORE_BUCKETS = [
	('no_candidate', None, None),
	('lt_0.40', 0.0, 0.4),
	('0.40_0.60', 0.4, 0.6),
	('0.60_0.75', 0.6, 0.75),
	('0.75_0.85', 0.75, 0.85),
	('gte_0.85', 0.85, None),
]


def normalize_name(value):
	text = str(value or '').lower()
	text = text.replace('&', 'and')
	return re.sub(r'[^a-z0-9]+', '', text)


def mapping_has_candidates(mapping_value):
	return isinstance(mapping_value[1], list) and len(mapping_value[1]) > 0


def candidate_names(mapping_value):
	return mapping_value[1] if isinstance(mapping_value[1], list) else []


def candidate_scores(mapping_value):
	return mapping_value[2] if isinstance(mapping_value[2], list) else []


def top_score(mapping_value):
	scores = candidate_scores(mapping_value)
	return scores[0] if scores else None


def score_bucket(score):
	if score is None:
		return 'no_candidate'
	for label, lower, upper in SCORE_BUCKETS[1:]:
		if (lower is None or score >= lower) and (upper is None or score < upper):
			return label
	return 'unknown'


def percentile(values, q):
	if not values:
		return None
	ordered = sorted(values)
	index = int((len(ordered) - 1) * q)
	return ordered[index]


def write_csv(path, rows, fieldnames):
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open('w', newline='', encoding='utf-8') as fp:
		writer = csv.DictWriter(fp, fieldnames=fieldnames, extrasaction='ignore')
		writer.writeheader()
		for row in rows:
			writer.writerow(row)


def write_json(path, payload):
	path.parent.mkdir(parents=True, exist_ok=True)
	with path.open('w', encoding='utf-8') as fp:
		json.dump(payload, fp, ensure_ascii=False, indent=2)


def summarize_layer1(mapping, categories_map, known_cable_names):
	category_counter = Counter()
	category_mapped = Counter()
	category_empty = Counter()
	candidate_count_counter = Counter()
	score_bucket_counter = Counter()
	top_cable_counter = Counter()
	all_scores = []
	top_scores = []
	structure_errors = []
	unknown_cables = Counter()

	for link, value in mapping.items():
		category = value[-1]
		category_counter[category] += 1
		cables = candidate_names(value)
		scores = candidate_scores(value)
		has_candidates = len(cables) > 0
		candidate_count_counter[len(cables)] += 1

		if has_candidates:
			category_mapped[category] += 1
			top_cable_counter.update(cables)
			all_scores.extend(scores)
			if scores:
				top_scores.append(scores[0])
			for cable in cables:
				if cable not in known_cable_names:
					unknown_cables[cable] += 1
			if len(cables) != len(scores) or not isinstance(value[3], list) or len(cables) != len(value[3]):
				structure_errors.append({'link': str(link), 'reason': '候选海缆、评分或登陆点数量不一致'})
		else:
			category_empty[category] += 1

		score_bucket_counter[score_bucket(top_score(value))] += 1

	category_map_sizes = {key: len(value) for key, value in categories_map.items()}
	category_rows = []
	for category in sorted(category_counter):
		total = category_counter[category]
		mapped = category_mapped[category]
		empty = category_empty[category]
		category_rows.append({
			'category': category,
			'total_links': total,
			'mapped_links': mapped,
			'empty_links': empty,
			'mapped_rate': round(mapped / total, 6) if total else 0,
			'category_map_links': category_map_sizes.get(category, 0),
		})

	score_rows = []
	for label, _, _ in SCORE_BUCKETS:
		score_rows.append({'score_bucket': label, 'links': score_bucket_counter[label]})

	summary = {
		'total_links': len(mapping),
		'mapped_links': sum(category_mapped.values()),
		'empty_links': sum(category_empty.values()),
		'mapped_rate': round(sum(category_mapped.values()) / len(mapping), 6) if mapping else 0,
		'categories': dict(category_counter),
		'category_map_sizes': category_map_sizes,
		'candidate_count_distribution': dict(candidate_count_counter),
		'score_distribution': {
			'count': len(all_scores),
			'min': percentile(all_scores, 0),
			'p25': percentile(all_scores, 0.25),
			'p50': percentile(all_scores, 0.5),
			'p75': percentile(all_scores, 0.75),
			'p90': percentile(all_scores, 0.9),
			'p99': percentile(all_scores, 0.99),
			'max': percentile(all_scores, 1),
		},
		'top_score_distribution': {
			'count': len(top_scores),
			'min': percentile(top_scores, 0),
			'p25': percentile(top_scores, 0.25),
			'p50': percentile(top_scores, 0.5),
			'p75': percentile(top_scores, 0.75),
			'p90': percentile(top_scores, 0.9),
			'p99': percentile(top_scores, 0.99),
			'max': percentile(top_scores, 1),
		},
		'structure_error_count': len(structure_errors),
		'unknown_cable_count': sum(unknown_cables.values()),
	}

	return {
		'summary': summary,
		'category_rows': category_rows,
		'score_rows': score_rows,
		'top_cable_rows': [
			{'cable': cable, 'links': count}
			for cable, count in top_cable_counter.most_common(100)
		],
		'structure_errors': structure_errors[:100],
		'unknown_cable_rows': [
			{'cable': cable, 'count': count}
			for cable, count in unknown_cables.most_common(100)
		],
	}


def compare_candidates(local_candidates, api_candidates):
	local = [item for item in local_candidates if item]
	api = [item for item in api_candidates if item]
	local_set = set(local)
	api_set = set(api)
	intersection = local_set & api_set
	union = local_set | api_set

	mrr = 0
	if intersection:
		best_rank = min(local.index(item) + 1 for item in intersection if item in local)
		mrr = 1 / best_rank

	return {
		'local_candidate_count': len(local),
		'api_candidate_count': len(api),
		'top1_agreement': bool(local and api and local[0] == api[0]),
		'top3_hit': bool(set(local[:3]) & api_set),
		'any_overlap': bool(intersection),
		'overlap_count': len(intersection),
		'jaccard': round(len(intersection) / len(union), 6) if union else None,
		'mrr': round(mrr, 6),
	}


def load_submarine_reference(processed_dir):
	cable_id_to_name = {}
	cable_name_to_id = {}
	known_cable_names = set()

	with (processed_dir / 'cables.csv').open(encoding='utf-8-sig', newline='') as fp:
		for row in csv.DictReader(fp):
			cable_id = row['cable_id']
			cable_name = row['cable_name']
			cable_id_to_name[cable_id] = cable_name
			cable_name_to_id[cable_name] = cable_id
			known_cable_names.add(cable_name)

	landing_points = {}
	with (processed_dir / 'landing_points.csv').open(encoding='utf-8-sig', newline='') as fp:
		for row in csv.DictReader(fp):
			landing_points[row['landing_point_id']] = {
				'name': row['name'],
				'country': row['country'],
				'lat': float(row['latitude']),
				'lon': float(row['longitude']),
			}

	cable_to_landing_points = defaultdict(list)
	with (processed_dir / 'cable_landing_points.csv').open(encoding='utf-8-sig', newline='') as fp:
		for row in csv.DictReader(fp):
			cable_name = cable_id_to_name.get(row['cable_id'], row['cable_id'])
			cable_to_landing_points[cable_name].append(row['landing_point_id'])

	name_index = {}
	for cable_id, cable_name in cable_id_to_name.items():
		name_index[normalize_name(cable_id)] = cable_name
		name_index[normalize_name(cable_name)] = cable_name

	return {
		'cable_id_to_name': cable_id_to_name,
		'cable_name_to_id': cable_name_to_id,
		'known_cable_names': known_cable_names,
		'landing_points': landing_points,
		'cable_to_landing_points': dict(cable_to_landing_points),
		'name_index': name_index,
	}


def extract_direct_cable_names(api_payload, reference):
	matches = []
	name_index = reference['name_index']

	def visit(obj, key_hint=''):
		if isinstance(obj, dict):
			for key, value in obj.items():
				hint = f'{key_hint}.{key}'.lower()
				visit(value, hint)
		elif isinstance(obj, list):
			for item in obj:
				visit(item, key_hint)
		elif isinstance(obj, str):
			hint = key_hint.lower()
			if not any(token in hint for token in ['cable', 'system', 'name', 'label', 'id']):
				return
			norm = normalize_name(obj)
			if norm in name_index:
				matches.append(name_index[norm])
				return
			for indexed, cable_name in name_index.items():
				if len(indexed) >= 8 and (indexed in norm or norm in indexed):
					matches.append(cable_name)
					return

	visit(api_payload)
	return list(dict.fromkeys(matches))


def _as_coordinate_pair(value):
	if isinstance(value, dict):
		lat = value.get('lat', value.get('latitude'))
		lon = value.get('lon', value.get('lng', value.get('longitude')))
		if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
			return float(lat), float(lon)
	if isinstance(value, list) and len(value) >= 2:
		a, b = value[0], value[1]
		if isinstance(a, (int, float)) and isinstance(b, (int, float)):
			# GeoJSON normally stores [lon, lat].
			if abs(a) <= 180 and abs(b) <= 90:
				return float(b), float(a)
			if abs(a) <= 90 and abs(b) <= 180:
				return float(a), float(b)
	return None


def _flatten_coordinates(value):
	pair = _as_coordinate_pair(value)
	if pair:
		return [pair]
	if isinstance(value, list):
		result = []
		for item in value:
			result.extend(_flatten_coordinates(item))
		return result
	return []


def extract_line_endpoints(api_payload):
	endpoints = []

	def visit(obj):
		if isinstance(obj, dict):
			for key, value in obj.items():
				if key.lower() in ['coordinates', 'coords', 'points', 'path', 'polyline', 'line']:
					coords = _flatten_coordinates(value)
					if len(coords) >= 2:
						endpoints.append((coords[0], coords[-1]))
				visit(value)
		elif isinstance(obj, list):
			coords = _flatten_coordinates(obj)
			if len(coords) >= 2:
				endpoints.append((coords[0], coords[-1]))
			for item in obj:
				visit(item)

	visit(api_payload)
	unique = []
	seen = set()
	for first, last in endpoints:
		key = (round(first[0], 4), round(first[1], 4), round(last[0], 4), round(last[1], 4))
		if key not in seen:
			seen.add(key)
			unique.append((first, last))
	return unique


def haversine_km(a, b):
	lat1, lon1 = math.radians(a[0]), math.radians(a[1])
	lat2, lon2 = math.radians(b[0]), math.radians(b[1])
	dlat = lat2 - lat1
	dlon = lon2 - lon1
	x = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
	return 6371.0 * 2 * math.atan2(math.sqrt(x), math.sqrt(1 - x))


def nearest_landing_points(coord, reference, threshold_km=75):
	matches = []
	for lp_id, lp in reference['landing_points'].items():
		distance = haversine_km(coord, (lp['lat'], lp['lon']))
		if distance <= threshold_km:
			matches.append((lp_id, distance))
	matches.sort(key=lambda item: item[1])
	return matches[:10]


def infer_cables_from_geometry(api_payload, reference, threshold_km=75):
	lp_to_cables = defaultdict(set)
	for cable, lp_ids in reference['cable_to_landing_points'].items():
		for lp_id in lp_ids:
			lp_to_cables[lp_id].add(cable)

	inferred = Counter()
	for first, last in extract_line_endpoints(api_payload):
		first_lps = nearest_landing_points(first, reference, threshold_km)
		last_lps = nearest_landing_points(last, reference, threshold_km)
		for lp_a, _ in first_lps:
			for lp_b, _ in last_lps:
				for cable in lp_to_cables[lp_a] & lp_to_cables[lp_b]:
					inferred[cable] += 1

	return [cable for cable, _ in inferred.most_common()]


def extract_api_candidates(api_payload, reference):
	direct = extract_direct_cable_names(api_payload, reference)
	if direct:
		return direct, 'direct_name'
	geometry = infer_cables_from_geometry(api_payload, reference)
	if geometry:
		return geometry, 'geometry_inferred'
	return [], 'none'
