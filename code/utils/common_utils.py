import pickle
from pathlib import Path
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed

import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import get_logger

from utils.merge_data import save_results_to_file
from utils.pickle_compat import load_pickle
from collections import namedtuple
from utils.geolocation_utils import generate_latlon_cluster_and_score_map, generate_categories, Location, MaxmindLocation
from utils.as_utils import generate_closest_submarine_org
from utils.traceroute_utils import load_all_links_and_ips_data, generate_test_case_links_and_ips_data

from submarine.telegeography_submarine import Cable, LandingPoints, get_all_latlon_locations_ball_tree
import math
import numpy as np
from itertools import product
from haversine import haversine, Unit

Cable = namedtuple('Cable', ['name', 'landing_points', 'length', 'owners', 'notes', 'rfs', 'other_info'])

logger = get_logger(__name__)

_CABLE_MAPPING_WORKER_CONTEXT = None


def get_cable_details():

	save_file = raw_path('submarine_data/cable_info_dict')

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			cable_dict = load_pickle(fp)
		return cable_dict
	else:
		print (f'Run the submarine module to generate necessary data')
		sys.exit(1)



def get_future_cables (cable_dict):
	return [cable for cable, values in cable_dict.items() if values.rfs >= 2022]



def get_submarine_owners():

	save_file = raw_path('submarine_data/owners_dict')

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			submarine_owners_dict = load_pickle(fp)
		return submarine_owners_dict
	else:
		print (f'Run the submarine module to generate necessary data')
		sys.exit(1)



def load_required_files (all_ips, links, mode=2, ip_version=4, sol_threshold=0.01, geolocation_threshold=0.6, ignore=True, geo_source_mode='maxmind_only'):

 # Ideally we want to load things straight away in which case we don't need all_ips and links
	geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated = generate_latlon_cluster_and_score_map (all_ips, ip_version=ip_version, mode=mode, threshold=sol_threshold, geo_source_mode=geo_source_mode)

	categories_map, categories_map_sol_validated = generate_categories(all_ips, links, geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, ip_version=ip_version, mode=mode, sol_threshold=sol_threshold, geolocation_threshold=geolocation_threshold, ignore=ignore)

	return geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, categories_map, categories_map_sol_validated



def get_sorted_mean_clusters (cluster):
    return [list(item) for item in list(map(lambda p: np.mean(p, axis=0), sorted(cluster, key=len, reverse=True)))]
    


def return_mean_and_len_clusters (ip_address, geolocation_latlon_cluster_and_scores_map):
    latlon_cluster, len_cluster, _ = geolocation_latlon_cluster_and_scores_map[ip_address]
    return (get_sorted_mean_clusters(latlon_cluster), sorted(len_cluster, reverse=True))


def get_cached_mean_and_len_clusters(ip_address, geolocation_latlon_cluster_and_scores_map, ip_cluster_cache=None):
    if ip_cluster_cache is None:
        return return_mean_and_len_clusters(ip_address, geolocation_latlon_cluster_and_scores_map)

    cached = ip_cluster_cache.get(ip_address)
    if cached is None:
        cached = return_mean_and_len_clusters(ip_address, geolocation_latlon_cluster_and_scores_map)
        ip_cluster_cache[ip_address] = cached
    return cached



def convert_degrees_to_randians(item):
    return tuple(map(math.radians, item))



def list_conversion_from_array (array):
    return [i.tolist() for i in array]



def get_landing_point_info (tree_index, landing_points_dict, latlon_dict, latlons):
    return landing_points_dict[latlon_dict[latlons[tree_index]]]



def prepare_landing_point_lookup(landing_points_dict, latlon_dict, latlons):
    landing_points_by_tree_index = []
    landing_point_cables_by_tree_index = []
    for latlon in latlons:
        landing_point = landing_points_dict[latlon_dict[latlon]]
        landing_points_by_tree_index.append(landing_point)
        landing_point_cables_by_tree_index.append(frozenset(landing_point.cable))
    return landing_points_by_tree_index, landing_point_cables_by_tree_index


def _latlon_pair_cache_key(category, latlon_pair):
    return (category, tuple(tuple(point) for point in latlon_pair))


def _attach_scores_to_candidate_cables(candidate_cables, latlon_pair, scores_pair):
    out = {}
    for cable, candidates in candidate_cables.items():
        out[cable] = [
            (latlon_pair, landing_points, scores_pair, dist_pairs)
            for landing_points, dist_pairs in candidates
        ]
    return out


def get_cable_for_given_latlon_pair (latlon_pair, tree, scores_pair, future_cables, landing_points_dict, latlon_dict, latlons, category, cable_dict=None, landing_points_by_tree_index=None, landing_point_cables_by_tree_index=None, candidate_cache=None):
    if candidate_cache is not None:
        cache_key = _latlon_pair_cache_key(category, latlon_pair)
        candidate_cables = candidate_cache.get(cache_key)
        if candidate_cables is not None:
            return _attach_scores_to_candidate_cables(candidate_cables, latlon_pair, scores_pair)
    else:
        cache_key = None

    if cable_dict is None:
        cable_dict = get_cable_details()

    if landing_points_by_tree_index is None or landing_point_cables_by_tree_index is None:
        landing_points_by_tree_index, landing_point_cables_by_tree_index = prepare_landing_point_lookup(landing_points_dict, latlon_dict, latlons)

    radians_latlon_pair = list(map(convert_degrees_to_randians, latlon_pair))
    candidate_cables = {}
    radius_increase = 50
    if 'te' in category:
    	current_radius = 500
    else:
    	current_radius = 1000
    match_count = 0
    while match_count < 2:
        ind, dist = tuple(map(list_conversion_from_array, tree.query_radius(radians_latlon_pair, current_radius/6371, return_distance=True, sort_results=True)))
        for index_pairs, dist_pairs in zip(product(ind[0], ind[1]), product(dist[0], dist[1])):
            if index_pairs[0] != index_pairs[1]:
                landing_point_1, landing_point_2 = landing_points_by_tree_index[index_pairs[0]], landing_points_by_tree_index[index_pairs[1]]
                cables = sorted(landing_point_cables_by_tree_index[index_pairs[0]] & landing_point_cables_by_tree_index[index_pairs[1]])
                cables = [cable for cable in cables if cable not in future_cables]
                if len(cables) > 0:
                    for cable in cables:
                        identified_cable = cable_dict[cable].name
                        scores_val = candidate_cables.get(identified_cable, [])
                        scores_val.append(((landing_point_1, landing_point_2), dist_pairs))
                        candidate_cables[identified_cable] = scores_val
                    match_count += 1
        current_radius += radius_increase
        if current_radius >= 1000:
            break
            
    if candidate_cache is not None:
        candidate_cache[cache_key] = candidate_cables
    return _attach_scores_to_candidate_cables(candidate_cables, latlon_pair, scores_pair)



def update_dict (dict_1, dict_2):
    out_dict = dict_1.copy()
    for k,v in dict_2.items():
        res = out_dict.get(k, [])
        res.extend(v)
        out_dict[k] = res
    return out_dict



def update_score_tuple (list_of_tuples_from_geolocation, owner_score_tuple):
    final_score_tuple = []
    for geolocation_tuple in list_of_tuples_from_geolocation:
        geolocation_tuple_list = list(geolocation_tuple)
        geolocation_tuple_list.append(owner_score_tuple)
        single_score_tuple = tuple(geolocation_tuple_list)
        final_score_tuple.append(single_score_tuple)
    return final_score_tuple



def try_load_pickle_file(path):

	try:
		with open(path, 'rb') as fp:
			return True, pickle.load(fp)
	except Exception as exc:
		logger.warning('Could not load %s: %s', path, exc)
		return False, None


def save_checkpoint_part(part_mapping, part_file):

	part_file.parent.mkdir(parents=True, exist_ok=True)
	save_results_to_file(part_mapping, str(part_file.parent), part_file.name)


def _init_cable_mapping_worker(latlon_cluster_and_score_map, category, tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict, landing_points_dict, latlon_dict, latlons):
	global _CABLE_MAPPING_WORKER_CONTEXT
	landing_points_by_tree_index, landing_point_cables_by_tree_index = prepare_landing_point_lookup(landing_points_dict, latlon_dict, latlons)
	_CABLE_MAPPING_WORKER_CONTEXT = {
	 'latlon_cluster_and_score_map': latlon_cluster_and_score_map,
	 'category': category,
	 'tree': tree,
	 'future_cables': future_cables,
	 'closest_submarine_org': closest_submarine_org,
	 'submarine_owners_dict': submarine_owners_dict,
	 'cable_dict': cable_dict,
	 'landing_points_dict': landing_points_dict,
	 'latlon_dict': latlon_dict,
	 'latlons': latlons,
	 'landing_points_by_tree_index': landing_points_by_tree_index,
	 'landing_point_cables_by_tree_index': landing_point_cables_by_tree_index,
	 'candidate_cache': {},
	 'ip_cluster_cache': {},
	}


def _generate_cable_mapping_part_worker(chunk_start, chunk_links, part_file):
	context = _CABLE_MAPPING_WORKER_CONTEXT
	if context is None:
		raise RuntimeError('Cable mapping worker context is not initialized')

	part_mapping = {}
	for ip_1, ip_2 in chunk_links:
		part_mapping[(ip_1, ip_2)] = generate_cable_mapping_for_single_link(
		 ip_1,
		 ip_2,
		 context['latlon_cluster_and_score_map'],
		 context['category'],
		 context['tree'],
		 context['future_cables'],
		 context['closest_submarine_org'],
		 context['submarine_owners_dict'],
		 context['cable_dict'],
		 context['landing_points_dict'],
		 context['latlon_dict'],
		 context['latlons'],
		 landing_points_by_tree_index=context['landing_points_by_tree_index'],
		 landing_point_cables_by_tree_index=context['landing_point_cables_by_tree_index'],
		 candidate_cache=context['candidate_cache'],
		 ip_cluster_cache=context['ip_cluster_cache'],
		)

	save_checkpoint_part(part_mapping, Path(part_file))
	return chunk_start, str(part_file), len(part_mapping)


def is_complete_mapping_file(final_file, expected_len):
	loaded, content = try_load_pickle_file(final_file)
	return loaded and len(content) == expected_len


def cleanup_checkpoint_parts(parts_directory):
	if not parts_directory.exists():
		logger.debug('Checkpoint directory does not exist: %s', parts_directory)
		return

	unexpected_paths = [path for path in parts_directory.iterdir() if not (path.is_file() and path.name.startswith('part_'))]
	for path in unexpected_paths:
		logger.warning('Keeping checkpoint directory because it contains non part_* item: %s', path)

	part_files = [path for path in parts_directory.iterdir() if path.is_file() and path.name.startswith('part_')]
	if not part_files:
		logger.debug('No checkpoint part files to clean: %s', parts_directory)
		return

	logger.info(
		'Complete output verified; deleting %d checkpoint part files from %s',
		len(part_files),
		parts_directory,
	)
	for part_file in sorted(part_files):
		try:
			part_file.unlink()
			logger.debug('Deleted checkpoint part file: %s', part_file)
		except OSError:
			logger.exception('Failed to delete checkpoint part file: %s', part_file)

	remaining_paths = list(parts_directory.iterdir())
	if not remaining_paths:
		try:
			parts_directory.rmdir()
			logger.info('Deleted empty checkpoint directory: %s', parts_directory)
		except OSError:
			logger.exception('Failed to delete empty checkpoint directory: %s', parts_directory)
	else:
		logger.warning('Checkpoint directory kept because it is not empty after part cleanup: %s', parts_directory)


def generate_cable_mapping_for_single_link(ip_1, ip_2, latlon_cluster_and_score_map, category, tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict, landing_points_dict, latlon_dict, latlons, landing_points_by_tree_index=None, landing_point_cables_by_tree_index=None, candidate_cache=None, ip_cluster_cache=None):

	link_all_scores_cable_map = {}

	mean_cluster_1, len_cluster_1 = get_cached_mean_and_len_clusters(ip_1, latlon_cluster_and_score_map, ip_cluster_cache)
	mean_cluster_2, len_cluster_2 = get_cached_mean_and_len_clusters(ip_2, latlon_cluster_and_score_map, ip_cluster_cache)

	scores_cable_map = {}

	for mean_cluster_combination, scores_combination in zip(product(mean_cluster_1, mean_cluster_2), product(len_cluster_1, len_cluster_2)):
		cables = get_cable_for_given_latlon_pair(
		 mean_cluster_combination, tree, scores_combination, future_cables,
		 landing_points_dict, latlon_dict, latlons, category,
		 cable_dict=cable_dict,
		 landing_points_by_tree_index=landing_points_by_tree_index,
		 landing_point_cables_by_tree_index=landing_point_cables_by_tree_index,
		 candidate_cache=candidate_cache,
		)
		for cable, cable_scores in cables.items():
			scores_cable_map.setdefault(cable, []).extend(cable_scores)

	org_1 = closest_submarine_org.get(ip_1, None)
	org_2 = closest_submarine_org.get(ip_2, None)

	org_1_cables_names, org_2_cables_names = set(), set()

	if org_1 or org_2:
		org_1_cables, org_2_cables = [], []
		if org_1:
			for org in org_1:
				org_1_cables.extend(submarine_owners_dict[org])
			for cable in org_1_cables:
				org_1_cables_names.add(cable_dict[cable].name)

		if org_2:
			for org in org_2:
				org_2_cables.extend(submarine_owners_dict[org])
			for cable in org_2_cables:
				org_2_cables_names.add(cable_dict[cable].name)

	if len(scores_cable_map) > 0:
		for cable, geolocation_tuples in scores_cable_map.items():
			owner_score_tuple = []
			if cable in org_1_cables_names:
				owner_score_tuple.append(1)
			else:
				owner_score_tuple.append(0)

			if cable in org_2_cables_names:
				owner_score_tuple.append(1)
			else:
				owner_score_tuple.append(0)

			link_all_scores_cable_map[cable] = update_score_tuple(geolocation_tuples, tuple(owner_score_tuple))

	return link_all_scores_cable_map


def generate_cable_mapping_for_given_category (category_links, latlon_cluster_and_score_map, category, tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict, landing_points_dict, latlon_dict, latlons, save_file = None, resume=True, checkpoint_interval=50000, progress_interval=5000, cleanup_checkpoints=True, mapping_workers=1):

	save_directory = output_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)
	landing_points_by_tree_index, landing_point_cables_by_tree_index = prepare_landing_point_lookup(landing_points_dict, latlon_dict, latlons)
	candidate_cache = {}
	ip_cluster_cache = {}

	if checkpoint_interval is None or checkpoint_interval <= 0:
		checkpoint_interval = len(category_links) if len(category_links) > 0 else 1
	if progress_interval is None or progress_interval <= 0:
		progress_interval = 5000
	mapping_workers = max(1, int(mapping_workers or 1))

	final_file = save_directory / save_file
	parts_directory = save_directory / 'checkpoints' / save_file
	if resume and final_file.is_file():
		loaded, content = try_load_pickle_file(final_file)
		if loaded and len(content) == len(category_links):
			logger.info('Resuming: found complete output %s; skipping %s', final_file, category)
			if cleanup_checkpoints:
				cleanup_checkpoint_parts(parts_directory)
			return content
		logger.info('Resuming: existing output %s is incomplete for current input; rebuilding from checkpoints', final_file)

	cable_mapping = {}
	pending_chunks = []

	for chunk_start in range(0, len(category_links), checkpoint_interval):
		chunk_end = min(chunk_start + checkpoint_interval, len(category_links))
		chunk_index = chunk_start // checkpoint_interval
		part_file = parts_directory / 'part_{:06d}'.format(chunk_index)
		expected_len = chunk_end - chunk_start

		if resume and part_file.is_file():
			loaded, part_mapping = try_load_pickle_file(part_file)
			if loaded and len(part_mapping) == expected_len:
				cable_mapping.update(part_mapping)
				logger.info('Resuming: loaded checkpoint %s with %d links', part_file, len(part_mapping))
				continue
			logger.info('Resuming: checkpoint %s is incomplete for current input; recalculating this part', part_file)

		if mapping_workers and mapping_workers > 1:
			pending_chunks.append((chunk_start, chunk_end, part_file))
			continue

		part_mapping = {}
		for count, (ip_1, ip_2) in enumerate(category_links[chunk_start:chunk_end], start=chunk_start):
			part_mapping[(ip_1, ip_2)] = generate_cable_mapping_for_single_link(
			 ip_1, ip_2, latlon_cluster_and_score_map, category, tree, future_cables,
			 closest_submarine_org, submarine_owners_dict, cable_dict, landing_points_dict,
			 latlon_dict, latlons,
			 landing_points_by_tree_index=landing_points_by_tree_index,
			 landing_point_cables_by_tree_index=landing_point_cables_by_tree_index,
			 candidate_cache=candidate_cache,
			 ip_cluster_cache=ip_cluster_cache,
			)

			processed = count + 1
			if processed % progress_interval == 0 or processed == len(category_links):
				logger.info('Finished %d of %d', processed, len(category_links))

		save_checkpoint_part(part_mapping, part_file)
		cable_mapping.update(part_mapping)

	if pending_chunks:
		logger.info('Processing %d checkpoint chunks for %s with %d workers', len(pending_chunks), category, mapping_workers)
		completed_parallel_chunks = []
		with ProcessPoolExecutor(
		 max_workers=mapping_workers,
		 initializer=_init_cable_mapping_worker,
		 initargs=(
		  latlon_cluster_and_score_map,
		  category,
		  tree,
		  future_cables,
		  closest_submarine_org,
		  submarine_owners_dict,
		  cable_dict,
		  landing_points_dict,
		  latlon_dict,
		  latlons,
		 ),
		) as executor:
			futures = {
			 executor.submit(
			  _generate_cable_mapping_part_worker,
			  chunk_start,
			  category_links[chunk_start:chunk_end],
			  str(part_file),
			 ): (chunk_start, chunk_end, part_file)
			 for chunk_start, chunk_end, part_file in pending_chunks
			}
			for future in as_completed(futures):
				chunk_start, chunk_end, part_file = futures[future]
				_, completed_part_file, part_len = future.result()
				expected_len = chunk_end - chunk_start
				if part_len != expected_len:
					raise ValueError(f'Checkpoint {completed_part_file} has {part_len} links, expected {expected_len}')
				completed_parallel_chunks.append((chunk_start, chunk_end, part_file, part_len))
				logger.info('Finished parallel checkpoint %s with %d links', part_file, part_len)

		for chunk_start, chunk_end, part_file, part_len in sorted(completed_parallel_chunks, key=lambda item: item[0]):
			expected_len = chunk_end - chunk_start
			loaded, part_mapping = try_load_pickle_file(part_file)
			if not loaded or len(part_mapping) != expected_len:
				raise ValueError(f'Could not validate checkpoint part {part_file}')
			cable_mapping.update(part_mapping)
			logger.info('Merged parallel checkpoint %s; accumulated %d of %d', part_file, len(cable_mapping), len(category_links))

	save_results_to_file(cable_mapping, str(save_directory), save_file)
	if cleanup_checkpoints and len(cable_mapping) == len(category_links):
		cleanup_checkpoint_parts(parts_directory)
	elif cleanup_checkpoints:
		logger.warning('Keeping checkpoint directory because complete output validation failed: %s', final_file)

	return cable_mapping



def general_cable_mapping_helper (categories_map, latlon_cluster_and_score_map, tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict, landing_points_dict, latlon_dict, latlons, max_links_to_process=None, server_id=None, mode=0, ip_version=4, resume=True, checkpoint_interval=50000, progress_interval=5000, cleanup_checkpoints=True, mapping_workers=1):

	cable_mapping_all_categories = {} 

	for category in categories_map:
		if category != 'de_te':
			if server_id:
				if server_id * max_links_to_process[category] > len(categories_map[category]):
					category_links = categories_map[category][(server_id - 1) * max_links_to_process[category]:]
				else:
					category_links = categories_map[category][(server_id - 1) * max_links_to_process[category]: server_id * max_links_to_process[category]]
			else:
				category_links = categories_map[category]
				if max_links_to_process and category in max_links_to_process:
					category_links = category_links[:max_links_to_process[category]]

			logger.info('For category %s, processing %d links', category, len(category_links))

			if mode == 0:
				save_file = 'cable_mapping_{}_v{}'.format(category, ip_version)
				if server_id:
					save_file += '_s{}'.format(server_id)

				cable_mapping = generate_cable_mapping_for_given_category(category_links, latlon_cluster_and_score_map, category, tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict, landing_points_dict, latlon_dict, latlons, save_file, resume=resume, checkpoint_interval=checkpoint_interval, progress_interval=progress_interval, cleanup_checkpoints=cleanup_checkpoints, mapping_workers=mapping_workers)

			else:
				save_file = 'cable_mapping_sol_validated_{}_v{}'.format(category, ip_version)
				if server_id:
					save_file += '_s{}'.format(server_id)

				cable_mapping = generate_cable_mapping_for_given_category(category_links, latlon_cluster_and_score_map, category, tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict, landing_points_dict, latlon_dict, latlons, save_file, resume=resume, checkpoint_interval=checkpoint_interval, progress_interval=progress_interval, cleanup_checkpoints=cleanup_checkpoints, mapping_workers=mapping_workers)

			cable_mapping_all_categories[category] = cable_mapping

	return cable_mapping_all_categories



def generate_cable_mapping (max_links_to_process=None, max_links_to_process_sol_validated=None, server_id=None, mode=2, ip_version=4, sol_threshold=0.01, geolocation_threshold=0.6, ignore=True, source_mode='ripe_only', geo_source_mode='maxmind_only', use_owner_score=True, resume=True, checkpoint_interval=50000, progress_interval=5000, cleanup_checkpoints=True, mapping_workers=1):

	links, all_ips = load_all_links_and_ips_data(ip_version=ip_version, source_mode=source_mode)
	geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, categories_map, categories_map_sol_validated = load_required_files (all_ips, links, mode=mode, ip_version=ip_version, sol_threshold=sol_threshold, geolocation_threshold=geolocation_threshold, ignore=ignore, geo_source_mode=geo_source_mode)

	cable_dict = get_cable_details()
	future_cables = set(get_future_cables(cable_dict))
	submarine_owners_dict = get_submarine_owners()
	landing_points_dict, latlon_dict, latlons, tree = get_all_latlon_locations_ball_tree()

	if use_owner_score:
		closest_submarine_org = generate_closest_submarine_org(all_ips, ip_version=ip_version)
	else:
		logger.info('Skipping IP-to-AS/ASRank owner scoring; owner score will be 0 for all candidate cables')
		closest_submarine_org = {}

	cable_mapping, cable_mapping_sol_validated = {}, {}

	if mode in [0, 2]:
		logger.info('Currently processing mode: %s', mode)
		cable_mapping = general_cable_mapping_helper(categories_map, geolocation_latlon_cluster_and_score_map, tree, 
		            future_cables, closest_submarine_org, submarine_owners_dict, cable_dict,
		            landing_points_dict, latlon_dict, latlons,
		            max_links_to_process=max_links_to_process, server_id=server_id,
		            mode=0, ip_version=ip_version, resume=resume,
		            checkpoint_interval=checkpoint_interval, progress_interval=progress_interval,
		            cleanup_checkpoints=cleanup_checkpoints,
		            mapping_workers=mapping_workers)

	if mode in [1, 2]:
		logger.info('Currently processing mode: %s', mode)
		cable_mapping_sol_validated = general_cable_mapping_helper(categories_map_sol_validated, geolocation_latlon_cluster_and_score_map_sol_validated, 
		                tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict,
		                landing_points_dict, latlon_dict, latlons,
		                max_links_to_process=max_links_to_process_sol_validated, server_id=server_id,
		                mode=1, ip_version=ip_version, resume=resume,
		                checkpoint_interval=checkpoint_interval, progress_interval=progress_interval,
		                cleanup_checkpoints=cleanup_checkpoints,
		                mapping_workers=mapping_workers)

	return cable_mapping, cable_mapping_sol_validated



def generate_cable_mapping_test(mode=2, ip_version=4, sol_threshold=0.01, geolocation_threshold=0.6, ignore=True, max_links_to_process=None, max_links_to_process_sol_validated=None, server_id=None, geo_source_mode='maxmind_only', use_owner_score=True):

	links, all_ips = generate_test_case_links_and_ips_data(ip_version=ip_version)
	geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, categories_map, categories_map_sol_validated = load_required_files (all_ips, links, mode=mode, ip_version=ip_version, sol_threshold=sol_threshold, geolocation_threshold=geolocation_threshold, ignore=ignore, geo_source_mode=geo_source_mode)

	cable_dict = get_cable_details()
	future_cables = set(get_future_cables(cable_dict))
	submarine_owners_dict = get_submarine_owners()
	landing_points_dict, latlon_dict, latlons, tree = get_all_latlon_locations_ball_tree()

	if use_owner_score:
		closest_submarine_org = generate_closest_submarine_org(all_ips, ip_version=ip_version)
	else:
		print ('Skipping IP-to-AS/ASRank owner scoring; owner score will be 0 for all candidate cables')
		closest_submarine_org = {}

	cable_mapping, cable_mapping_sol_validated = {}, {}

	if mode in [0, 2]:
		print (f'Currently processing mode : {mode}')
		cable_mapping = general_cable_mapping_helper(categories_map, geolocation_latlon_cluster_and_score_map, tree, 
		            future_cables, closest_submarine_org, submarine_owners_dict, cable_dict,
		            landing_points_dict, latlon_dict, latlons,
		            max_links_to_process=max_links_to_process, server_id=server_id,
		            mode=0, ip_version=ip_version)

	if mode in [1, 2]:
		print (f'Currently processing mode : {mode}')
		cable_mapping_sol_validated = general_cable_mapping_helper(categories_map_sol_validated, geolocation_latlon_cluster_and_score_map_sol_validated, 
		                tree, future_cables, closest_submarine_org, submarine_owners_dict, cable_dict,
		                landing_points_dict, latlon_dict, latlons,
		                max_links_to_process=max_links_to_process_sol_validated, server_id=server_id,
		                mode=1, ip_version=ip_version)

	return cable_mapping, cable_mapping_sol_validated





def get_load_all_cable_mapping_merged_output(mode=2, ip_version=4):

	save_directory = output_path('mapping_outputs')

	categories = ['bg_oc', 'og_oc', 'bb_oc', 'bg_te', 'og_te', 'bb_te']

	cable_mapping, cable_mapping_sol_validated = {}, {}

	cable_mapping_files = ['cable_mapping_{}_v{}_merged'.format(category, ip_version) for category in categories]
	cable_mapping_sol_validated_files = ['cable_mapping_sol_validated_{}_v{}_merged'.format(category, ip_version) for category in categories]

	mapping = {}
	mapping_sol_validated = {}

	if mode in [0, 2]:
		for index, file in enumerate(cable_mapping_files):
			with open(save_directory/file, 'rb') as fp:
				content = pickle.load(fp)
			mapping[categories[index]] = content

			print (f'Only geolocation: Finished loading for {categories[index]}')

			del(content)

	if mode in [1, 2]:
		for index, file in enumerate(cable_mapping_sol_validated_files):
			with open(save_directory/file, 'rb') as fp:
				content = pickle.load(fp)
			mapping_sol_validated[categories[index]] = content

			print (f'SoL validated: Finished loading for {categories[index]}')

			del(content)

	return mapping, mapping_sol_validated



def generate_reverse_landing_points_dict ():

	landing_points_dict, latlon_dict, latlons, tree = get_all_latlon_locations_ball_tree()
	return {v._replace(cable=tuple(v.cable)) : k for k, v in landing_points_dict.items()}



# Temporarily placing the loading cable to lp ids function here, will have to move this to the proper module
def load_cable_to_lp_ids ():

	with open(str(raw_path('submarine_data/cable_to_connected_location_ids')), 'rb') as fp:
		cable_to_lp_ids = load_pickle(fp)

	return cable_to_lp_ids



def prepare_cable_to_lp_id_sets(cable_to_lp_ids):
	return {
	 cable: [frozenset(item) for item in connected_points]
	 for cable, connected_points in cable_to_lp_ids.items()
	}


def get_landing_point_id_from_landing_points_list (landing_points_list, reverse_landing_points_dict, landing_point_id_cache=None):

	cache_key = None
	if landing_point_id_cache is not None:
		cache_key = tuple(landing_point._replace(cable=tuple(landing_point.cable)) for landing_point in landing_points_list)
		cached = landing_point_id_cache.get(cache_key)
		if cached is not None:
			return cached

	landing_points_ids = []
	for landing_point in landing_points_list:
		landing_points_id = reverse_landing_points_dict.get(landing_point._replace(cable=tuple(landing_point.cable)), '')
		landing_points_ids.append(landing_points_id)

	result = tuple(landing_points_ids)
	if landing_point_id_cache is not None:
		landing_point_id_cache[cache_key] = result
	return result



def assign_overall_score (score_tuple, weight_tuple, category):

	if 'te' in category:
		scale_factor = 0.5
	else:
		scale_factor = 1

	constant_factor = 0.5

	# score tuple
	# 	0 -> IP geolocation
	#	1 -> Landing points details
	#	2 -> geolocation score (geolocation clustering score)
	#	3 -> distance from IP geolocation to identified landing point
	#	4 -> as owner scores

	geolocation_score = sum(score_tuple[2]) * weight_tuple[0]

	# Distance score should be ideally 0, so that we get reverse distance score of 2
	# Worse case we get distance score of 2, which implies both the points are 1000 km away
	distance_score = sum(score_tuple[3]) / (1000/6371)
	reverse_distance_score = (2 - distance_score) * weight_tuple[1]

	as_owner_score = sum(score_tuple[4]) * weight_tuple[2]

	# Check to help with re-classification of link to definite terrestrial
	# If the landing points are way to far (ie., 2x times the actual distance between the IPs)
	if 2 * haversine(score_tuple[0][0], score_tuple[0][1], unit = Unit.RADIANS) < sum(score_tuple[3]):
		return None 
	else:
		return (score_tuple[1], (geolocation_score + reverse_distance_score + as_owner_score) * constant_factor * scale_factor)



def _get_cached_lp_id_set(lp_id, lp_id_set_cache=None):
	if lp_id_set_cache is None:
		return set(lp_id)
	cached = lp_id_set_cache.get(lp_id)
	if cached is None:
		cached = frozenset(lp_id)
		lp_id_set_cache[lp_id] = cached
	return cached


def select_cables_for_given_link (link, scores_and_cables, weight_tuple, de_te_additions, cable_to_lp_ids, category, reverse_landing_points_dict,threshold=0.05, cable_to_lp_id_sets=None, landing_point_id_cache=None, lp_id_set_cache=None):

	ret_dict = {}

	# de_te_additions to take note of all links that are getting re-classified as definite terrestrial

	# This means we haven't been able to map to any cable
	if len(scores_and_cables) == 0:
		return {}, 0

 # Let's examine all the predicted cables
	for cable, score_tuples in scores_and_cables.items():
		scores = []
		for score_tuple in score_tuples:
			score_for_tuple = assign_overall_score(score_tuple, weight_tuple, category)
			res = True
			if score_for_tuple:
				lp_id = get_landing_point_id_from_landing_points_list(score_for_tuple[0], reverse_landing_points_dict, landing_point_id_cache)
				try:
					lp_id_set = _get_cached_lp_id_set(lp_id, lp_id_set_cache)
					# Check to see if both the landing points are connected
					if cable_to_lp_id_sets is not None:
						cable_connected_points = cable_to_lp_id_sets[cable]
						res = any(len(lp_id_set & connected_points) == 2 for connected_points in cable_connected_points)
					else:
						cable_connected_points = cable_to_lp_ids[cable]
						res = any(len(lp_id_set & set(item)) == 2 for item in cable_connected_points)
				except:
					pass 
				if res:
					score_for_tuple = (lp_id, score_for_tuple[-1])
					scores.append(score_for_tuple)

		if len(scores) > 0:
			max_score = max(scores, key=lambda x: x[1])
			# Checking if other selections are within the threshold
			ret_cable_scores = [item for item in sorted(scores, key = lambda x: x[1], reverse=True) if (max_score[1] - item[1]) <= max_score[1] * threshold]
			ret_dict[cable] = ret_cable_scores

	if len(ret_dict) > 0:
		return {k: v for k, v in sorted(ret_dict.items(), key=lambda item: item[1][0][1], reverse=True)}, 0
	else:
		if res == True: # Means that we never went inside if score_for_tuple (otherwise, if we went inside and got res = True, then length won't be 0)
			de_te_additions.append(link)
			return {}, 1
		return {}, 0



def generate_final_mapping_helper (cable_mapping, de_te_additions, cable_to_lp_ids, reverse_landing_points_dict, threshold=0.05):

	link_to_cable_and_score_mapping = {}
	cable_to_lp_id_sets = prepare_cable_to_lp_id_sets(cable_to_lp_ids)
	landing_point_id_cache = {}
	lp_id_set_cache = {}

	for category, category_cable_mapping in cable_mapping.items():
		print (f'Currenlty processing {category}')
		for count, (link, scores_and_cables) in enumerate(category_cable_mapping.items()):
		 # Getting the scores dict
			cables, de_te_added = select_cables_for_given_link(
			 link, scores_and_cables, (0.5, 0.4, 0.1), de_te_additions,
			 cable_to_lp_ids, category, reverse_landing_points_dict,
			 threshold=threshold,
			 cable_to_lp_id_sets=cable_to_lp_id_sets,
			 landing_point_id_cache=landing_point_id_cache,
			 lp_id_set_cache=lp_id_set_cache,
			)

			if len(cables) > 0:
			 # Earlier we selected all cables where each landing point was within 0.05 of that particular cable's max value
			 # Now we prune based on overall max values
				all_max_scores = [content[0][-1] for content in cables.values()]
				overall_max_score = max(all_max_scores)
				all_max_scores_above_threshold = [score for score in all_max_scores if (overall_max_score - score) <= overall_max_score * threshold]

				selected_cables = []
				all_cables = list(cables.keys())

				for idx, cnt in enumerate(all_max_scores_above_threshold):
					cable_name = all_cables[idx]
					selected_cables.append(cable_name)

				score = all_max_scores_above_threshold

				selected_landing_points = []
				for cable in selected_cables:
					contents = cables[cable]
					single_cable_landing_points = []
					# Just re-examining again the selected landing points per cable based on the overall max score
					for single_content in contents:
						c_score = single_content[-1]
						if (overall_max_score - c_score) <= overall_max_score * threshold:
							landing_points = single_content[0]
							single_cable_landing_points.append(landing_points)
					landing_points = list(set(landing_points))
					selected_landing_points.append(single_cable_landing_points)

			else:
				selected_cables = ''
				score = 0
				selected_landing_points = ''

   # Let's generate the final scores file only if it satisfied the additional de_te constraints
			if de_te_added == 0:
				link_to_cable_and_score_mapping[link] = (len(cables), selected_cables, score, selected_landing_points, category)

			if count % 100000 == 0:
				print (f'Finised processing {count} of {len(category_cable_mapping)} links')


	return link_to_cable_and_score_mapping



def generate_final_mapping (mode=2, ip_version=4, threshold=0.05):

	save_directory = result_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	# Let's first load all the merged output for each category
	cable_mapping, cable_mapping_sol_validated = get_load_all_cable_mapping_merged_output(mode=mode, ip_version=ip_version)

	# Loading the cable to connected landing points dict
	cable_to_lp_ids = load_cable_to_lp_ids()

	reverse_landing_points_dict = generate_reverse_landing_points_dict()

	de_te_additions, de_te_additions_sol_validated = [], []

	link_to_cable_and_score_mapping, link_to_cable_and_score_mapping_sol_validated = {}, {}

	if mode in [0, 2]:
		link_to_cable_and_score_mapping = generate_final_mapping_helper(cable_mapping, de_te_additions, cable_to_lp_ids, reverse_landing_points_dict, threshold=threshold)
		save_results_to_file(link_to_cable_and_score_mapping, str(save_directory), 'link_to_cable_and_score_mapping_v{}'.format(ip_version))
		save_results_to_file(de_te_additions, str(save_directory), 'additional_de_te_links_v{}'.format(ip_version))

		del(link_to_cable_and_score_mapping)
		del(de_te_additions)

	if mode in [1, 2]:
		link_to_cable_and_score_mapping_sol_validated = generate_final_mapping_helper(cable_mapping_sol_validated, de_te_additions_sol_validated, cable_to_lp_ids, reverse_landing_points_dict, threshold=threshold)
		save_results_to_file(link_to_cable_and_score_mapping_sol_validated, str(save_directory), 'link_to_cable_and_score_mapping_sol_validated_v{}'.format(ip_version))
		save_results_to_file(de_te_additions_sol_validated, str(save_directory), 'additional_de_te_links_sol_validated_v{}'.format(ip_version))

		del(link_to_cable_and_score_mapping_sol_validated)
		del(de_te_additions_sol_validated)

 # return link_to_cable_and_score_mapping, de_te_additions, link_to_cable_and_score_mapping_sol_validated, de_te_additions_sol_validated



def generate_final_mapping_test (cable_mapping, cable_mapping_sol_validated, mode=2, ip_version=4, threshold=0.05):

	save_directory = result_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	# Loading the cable to connected landing points dict
	cable_to_lp_ids = load_cable_to_lp_ids()

	reverse_landing_points_dict = generate_reverse_landing_points_dict()

	de_te_additions, de_te_additions_sol_validated = [], []

	link_to_cable_and_score_mapping, link_to_cable_and_score_mapping_sol_validated = {}, {}

	if mode in [0, 2]:
		link_to_cable_and_score_mapping = generate_final_mapping_helper(cable_mapping, de_te_additions, cable_to_lp_ids, reverse_landing_points_dict, threshold=threshold)
		save_results_to_file(link_to_cable_and_score_mapping, str(save_directory), 'link_to_cable_and_score_mapping_v{}'.format(ip_version))
		save_results_to_file(de_te_additions, str(save_directory), 'additional_de_te_links_v{}'.format(ip_version))

		del(link_to_cable_and_score_mapping)
		del(de_te_additions)

	if mode in [1, 2]:
		link_to_cable_and_score_mapping_sol_validated = generate_final_mapping_helper(cable_mapping_sol_validated, de_te_additions_sol_validated, cable_to_lp_ids, reverse_landing_points_dict, threshold=threshold)
		save_results_to_file(link_to_cable_and_score_mapping_sol_validated, str(save_directory), 'link_to_cable_and_score_mapping_sol_validated_v{}'.format(ip_version))
		save_results_to_file(de_te_additions_sol_validated, str(save_directory), 'additional_de_te_links_sol_validated_v{}'.format(ip_version))

		del(link_to_cable_and_score_mapping_sol_validated)
		del(de_te_additions_sol_validated)



def regenerate_categories_map_helper (categories_map, de_te_additions, ip_version=4):

	new_categories_map = { 'bg_oc': [], 'og_oc': [], 'bb_oc': [],
	        'bg_te': [], 'og_te': [], 'bb_te': [], 'de_te': [] }

	for key in new_categories_map:
		if key != 'de_te':
			local_var = set(categories_map[key]).difference(set(de_te_additions))
			new_categories_map[key] = list(local_var)
			print (f'For category {key}, earlier {len(categories_map[key])}, it is now {len(new_categories_map[key])}')
		else:
			local_var = categories_map[key].copy()
			local_var.extend(de_te_additions)
			new_categories_map[key] = list(set(local_var))
			print (f'For category {key}, earlier {len(categories_map[key])}, it is now {len(new_categories_map[key])}')

	return new_categories_map


def regenerate_categories_map (mode=2, ip_version=4):

	intermediate_directory = output_path('mapping_outputs')
	save_directory = result_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	if mode in [0, 2]:
		with open(intermediate_directory/'categories_map_v{}'.format(ip_version), 'rb') as fp:
			categories_map = pickle.load(fp)

		with open(save_directory/'additional_de_te_links_v{}'.format(ip_version), 'rb') as fp:
			de_te_additions = pickle.load(fp)

		new_categories_map = regenerate_categories_map_helper(categories_map, de_te_additions, ip_version=ip_version)
		save_results_to_file(new_categories_map, str(save_directory), 'categories_map_updated_v{}'.format(ip_version))

	if mode in [1, 2]:
		with open(intermediate_directory/'categories_map_sol_validated_v{}'.format(ip_version), 'rb') as fp:
			categories_map_sol_validated = pickle.load(fp)

		with open(save_directory/'additional_de_te_links_sol_validated_v{}'.format(ip_version), 'rb') as fp:
			de_te_additions_sol_validated = pickle.load(fp)

		new_categories_map_sol_validated = regenerate_categories_map_helper(categories_map_sol_validated, de_te_additions_sol_validated, ip_version=ip_version)
		save_results_to_file(new_categories_map_sol_validated, str(save_directory), 'categories_map_sol_validated_updated_v{}'.format(ip_version))



if __name__ == '__main__':

	operation = str(sys.argv[1])

	if operation == 'g':
		mode = int(sys.argv[2])
		ip_version = int(sys.argv[3])
		server_id = int(sys.argv[4])

		print (f'Generating cable mapping with mode = {mode}, ip_version = {ip_version} and at server_id = {server_id}')

		categories = ['bg_oc', 'og_oc', 'bb_oc', 'bg_te', 'og_te', 'bb_te']

		max_links_to_process, max_links_to_process_sol_validated = {}, {}

		for count, category in enumerate(categories):
			max_links_to_process[category] = int(sys.argv[count+5])
			max_links_to_process_sol_validated[category] = int(sys.argv[count+11])

		print (f'max_links_to_process : {max_links_to_process}')
		print (f'max_links_to_process_sol_validated : {max_links_to_process_sol_validated}')

		cable_mapping, cable_mapping_sol_validated = generate_cable_mapping(max_links_to_process, max_links_to_process_sol_validated, server_id, mode, ip_version, sol_threshold=0.05)

	if operation == 'n':
		mode = int(sys.argv[2])
		ip_version = int(sys.argv[3])
		_, cable_mapping_sol_validated = generate_cable_mapping(mode=mode, ip_version=ip_version, sol_threshold=0.05)

	if operation == 'f':
		generate_final_mapping(mode=1, ip_version=4, threshold=0.05)
		regenerate_categories_map (mode=1, ip_version=4)

	if operation == 't':

		cable_mapping, cable_mapping_sol_validated = generate_cable_mapping_test(mode=2, ip_version=4, sol_threshold=0.05, geolocation_threshold=0.6, ignore=True, max_links_to_process=None, max_links_to_process_sol_validated=None, server_id=None)
		generate_final_mapping_test(cable_mapping, cable_mapping_sol_validated, mode=2, ip_version=4, threshold=0.05)
