import pickle, sys
from haversine import haversine
from pathlib import Path
from collections import Counter

from sklearn.cluster import DBSCAN
import numpy as np

import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

from location.generate_ground_truth_ips_and_split import load_rtt_proximity_ground_truth_data
from location.maxmind_utils import generate_locations_for_list_of_ips as maxmind_func
from location.ripe_geolocation_utils import generate_location_for_list_of_ips_ripe as ripe_func
from location.caida_geolocation_utils import generate_location_for_list_of_ips as caida_func

from location.maxmind_utils import MaxmindLocation 
from location.ipgeolocation_utils import Location

import reverse_geocode
import pycountry_convert as pc


def load_and_process_ground_truth_data():
 
	save_file = str(output_path('ip_data/ip_to_location_ground_truth'))

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			ip_to_location = pickle.load(fp)

	else:
		ip_to_location = load_rtt_proximity_ground_truth_data()

	return ip_to_location



def get_distances_for_given_source (source_ip_to_coordinates, ip_to_location):

	distances = {k: haversine(source_ip_to_coordinates[k], ip_to_location[k]) for k in source_ip_to_coordinates.keys() if source_ip_to_coordinates[k] != None}

	return distances



def process_results_from_all_sources(ip_to_location):

	maxmind_location, skipped_ips = maxmind_func(ip_to_location.keys())

	maxmind_ip_to_coordinates = {k: (float(v.latitude), float(v.longitude)) for k,v in maxmind_location.items()}

	maxmind_distances = get_distances_for_given_source(maxmind_ip_to_coordinates, ip_to_location)

	print (f'From maxmind, we have results for {len(maxmind_distances)} of {len(ip_to_location)} IPs')

	ripe_location = ripe_func(ip_to_location.keys())

	ripe_ip_to_coordinates = {k: (float(v[-3]), float(v[-2])) for k,v in ripe_location.items() if v[2] != ''}

	ripe_distances = get_distances_for_given_source(ripe_ip_to_coordinates, ip_to_location)

	print (f'From RIPE, we have results for {len(ripe_distances)} of {len(ip_to_location)} IPs')

	caida_location = caida_func(ip_to_location.keys())

	caida_ip_to_coordinates = {k: (float(v[-3]), float(v[-2])) for k,v in caida_location.items() if v[3] != ''}

	caida_distances = get_distances_for_given_source(caida_ip_to_coordinates, ip_to_location)

	print (f'From CAIDA, we have results for {len(caida_distances)} of {len(ip_to_location)} IPs')

	# Ideally, we want to run across servers and merge results, for now, we are directly loading the file which did all that
	save_file = str(output_path('location_data/iplocation_location_output_v4_default'))

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			iplocation_location = pickle.load(fp)

	else:
		print (f'File not generated, generate the output by running iplocation script across servers and merge results')
		sys.exit(1)

	iplocation_ip_to_coordinates = {}
	iplocation_missed = [0] * 8
	for k in ip_to_location.keys():
		v = iplocation_location.get(k, None)
		if v:
			ip_location = []
			for index, item in enumerate(v):
				try:
					iplocation_latlon = (float(item.latitude.decode()), float(item.longitude.decode()))
					ip_location.append(iplocation_latlon)
				except:
					iplocation_missed[index] += 1
					ip_location.append(None)
					pass

			if len(ip_location) > 0:
				iplocation_ip_to_coordinates[k] = ip_location

	iplocation_distances = {}

	for index in range(8):
		source_ip_to_coordinates = {k: v[index] for k,v in iplocation_ip_to_coordinates.items()}
		iplocation_distances[index] = get_distances_for_given_source(source_ip_to_coordinates, ip_to_location)

	print (f'From IPlocation, we have {list(map(len, iplocation_distances.values()))} of {len(ip_to_location)} IPs')

	return maxmind_distances, ripe_distances, caida_distances, iplocation_distances, maxmind_ip_to_coordinates, ripe_ip_to_coordinates, caida_ip_to_coordinates, iplocation_ip_to_coordinates


def generate_distances_files (maxmind_distances, ripe_distances, caida_distances, iplocation_distances):

	save_directory = 'plot_results'

	ripe_file = 'ripe_distances.txt'

	with open(save_directory+'/'+ripe_file, 'w') as fp:
		for distance in ripe_distances.values():
			fp.write(str(distance)+'\n')

	caida_file = 'caida_distances.txt'

	with open(save_directory+'/'+caida_file, 'w') as fp:
		for distance in caida_distances.values():
			fp.write(str(distance)+'\n')

	maxmind_file = 'maxmind_distances.txt'

	with open(save_directory+'/'+maxmind_file, 'w') as fp:
		for distance in maxmind_distances.values():
			fp.write(str(distance)+'\n')

	iplocation_file = 'iplocation_distances_{}.txt'

	for key, value in iplocation_distances.items():
		with open(save_directory+'/'+iplocation_file.format(key), 'w') as fp:
			for distance in value.values():
				fp.write(str(distance)+'\n')



def is_location_correct (distance, threshold=50):

	return int(distance <= threshold)



def get_how_many_have_good_geolocation (maxmind_distances, ripe_distances, caida_distances, iplocation_distances, ip_to_location, threshold=50):

	got_correct = {}

	for ip in ip_to_location:
		total = 0
		correct = 0
		ripe_d = ripe_distances.get(ip, None)
		if ripe_d:
			total += 1
			correct += is_location_correct(ripe_d, threshold)

		caida_d = caida_distances.get(ip, None)
		if caida_d:
			total += 1
			correct += is_location_correct(caida_d, threshold)

		maxmind_d = maxmind_distances.get(ip, None)
		if maxmind_d:
			total += 1
			correct += is_location_correct(maxmind_d, threshold)

		for key, value in iplocation_distances.items():
			single_ip_d = value.get(ip, None)
			if single_ip_d:
				total += 1
				correct += is_location_correct(single_ip_d, threshold)
 
		if total > 0:
			got_correct[ip] = correct/total

	print (Counter(got_correct.values()))



def get_cluster_as_list (clusters, original_list):

	return_list = []
	start = 0
	for index, value in enumerate(clusters):
	    if start == value:
	        return_list.append([])
	        start += 1
	    return_list[value].append(original_list[index])
	len_list = [len(item)/len(clusters) for item in return_list]
	return return_list, len_list



def cluster_locations(locations_list):
    cluster = DBSCAN(eps=50/6371., min_samples = 1, algorithm='ball_tree', metric='haversine', leaf_size=2).fit_predict(np.radians(locations_list))
    return get_cluster_as_list(cluster, locations_list)


def get_sorted_mean_clusters (cluster):
    return [list(item) for item in list(map(lambda p: np.mean(p, axis=0), sorted(cluster, key=len, reverse=True)))]


def update_correctness_dicts(source_location, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, source, correctness, threshold=50):

	country_to_continent_map = {'VA': 'EU'}

	distance = haversine(source_location, original_location)
	if distance <= threshold:
		current_value = city_scores.get(source, 0)
		city_scores[source] = current_value + 1
		correctness[0] += 1
 
	country = reverse_geocode.search([source_location])[0]['country_code']
	if country == original_country:
		current_value = country_scores.get(source, 0)
		country_scores[source] = current_value + 1
		correctness[1] += 1

	try:
		continent = pc.country_alpha2_to_continent_code(country)
	except:
		if country in country_to_continent_map:
			continent = country_to_continent_map[country]
		else:
			print (f'Things failed for country: {country}')

	if continent == original_continent:
		current_value = continent_scores.get(source, 0)
		continent_scores[source] = current_value + 1
		correctness[2] += 1


	current_value = total_counts.get(source, 0)
	total_counts[source] = current_value + 1


def get_percentage_correctness_at_various_granularities (maxmind_ip_to_coordinates, ripe_ip_to_coordinates, caida_ip_to_coordinates, iplocation_ip_to_coordinates, ip_to_location, threshold=50):

	city_scores = {}
	country_scores = {}
	continent_scores = {}
	total_counts = {}

	for ip, location in ip_to_location.items():
		original_location = location
		original_country = reverse_geocode.search([location])[0]['country_code']
		original_continent = pc.country_alpha2_to_continent_code(original_country)

		correctness = [0] * 3
		updated = False
		all_results = []

		ripe_location = ripe_ip_to_coordinates.get(ip, None)
		if ripe_location:
			all_results.append(ripe_location)
			update_correctness_dicts(ripe_location, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'ripe', correctness, threshold=50)
			update = True

		caida_location = caida_ip_to_coordinates.get(ip, None)
		if caida_location:
			all_results.append(caida_location)
			update_correctness_dicts(caida_location, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'caida', correctness, threshold=50)
			update = True

		maxmind_location = maxmind_ip_to_coordinates.get(ip, None)
		if maxmind_location:
			all_results.append(maxmind_location)
			update_correctness_dicts(maxmind_location, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'maxmind', correctness, threshold=50)
			update = True

		iplocation_location = iplocation_ip_to_coordinates.get(ip, None)
		if iplocation_location:
			if len(iplocation_location) != 8:
				print ('Things are bad, recheck your code')
			for index, single_iplocation in enumerate(iplocation_location):
				if single_iplocation:
					all_results.append(single_iplocation)
					update_correctness_dicts(single_iplocation, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'iplocation_{}'.format(index), correctness, threshold=50)
					update = True

		if len(all_results) > 0:
			clusters, len_list = cluster_locations(all_results)
			max_cluster = get_sorted_mean_clusters(clusters)[0]
			update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'Nautilus', [0] * 3, threshold=50)
			if max(len_list) >= 0.6:
				update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'threshold_6', [0] * 3, threshold=50)
			if max(len_list) >= 0.5:
				update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'threshold_5', [0] * 3, threshold=50)
			if max(len_list) >= 0.7:
				update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'threshold_7', [0] * 3, threshold=50)
			if max(len_list) >= 0.8:
				update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'threshold_8', [0] * 3, threshold=50)
			if max(len_list) >= 0.65:
				update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'threshold_65', [0] * 3, threshold=50)
			if max(len_list) >= 0.55:
				update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'threshold_55', [0] * 3, threshold=50)
			if max(len_list) >= 0.75:
				update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'threshold_75', [0] * 3, threshold=50)
   


		if update:
			if correctness[0] > 0:
				current_value = city_scores.get('atleast_one_source', 0)
				city_scores['atleast_one_source'] = current_value + 1
			if correctness[1] > 0:
				current_value = country_scores.get('atleast_one_source', 0)
				country_scores['atleast_one_source'] = current_value + 1

			if correctness[2] > 0:
				current_value = continent_scores.get('atleast_one_source', 0)
				continent_scores['atleast_one_source'] = current_value + 1

			current_value = total_counts.get('atleast_one_source', 0)
			total_counts['atleast_one_source'] = current_value + 1

	print ('*' * 50)
	print ('City-level accuracies: ')
	for source, count in city_scores.items():
		print (f'{source}: {count / len(ip_to_location) * 100} %')
		print (f'{source} total count: {total_counts[source]}')
		print (f'{source} total count %age : {total_counts[source]/len(ip_to_location)*100}')

	print ('*' * 50)
	print ('Country-level accuracies: ')
	for source, count in country_scores.items():
		print (f'{source}: {count / len(ip_to_location) * 100} %')

	print ('*' * 50)
	print ('Continent-level accuracies: ')
	for source, count in continent_scores.items():
		print (f'{source}: {count / len(ip_to_location) * 100} %')


def get_overlap_with_sol_validated (ip_to_location):

	with open(str(output_path('location_data/all_validated_ip_location_v4')), 'rb') as fp:
		sol_validated_locations = pickle.load(fp)

	overlap = list(set(ip_to_location) & set(sol_validated_locations))

	print (f'We have an overlap of {len(overlap)} IPs')

	return {ip: ip_to_location[ip] for ip in overlap}, sol_validated_locations



def get_percentage_correctness_sol_validated (overlap_ip_to_location, sol_validated_locations, threshold=50, sol_threshold=0.05):

	city_scores = {}
	country_scores = {}
	continent_scores = {}
	total_counts = {}

	print (f'Threshold : {sol_threshold}')

	for ip, location in overlap_ip_to_location.items():
		original_location = location
		original_country = reverse_geocode.search([original_location])[0]['country_code']
		original_continent = pc.country_alpha2_to_continent_code(original_country)

		ip_result = []

		sol_validated_ip_val = sol_validated_locations.get(ip, None)
		if sol_validated_ip_val:
			location_index = sol_validated_ip_val['location_index']
			coordinates = sol_validated_ip_val['coordinates']
			for index, total_count in enumerate(sol_validated_ip_val['total_count']):
				if total_count > 0:
					coordinate_index = location_index.index(index)
					if (sol_validated_ip_val['penalty_count'][index] / total_count) <= sol_threshold:
						ip_result.append(coordinates[coordinate_index])

  
		if len(ip_result) > 0:
   
			distances = [haversine(item, original_location) for item in ip_result]
			is_city = [item <= threshold for item in distances]
   
			if any(is_city):
				current_value = city_scores.get('atleast_one_sol', 0)
				city_scores['atleast_one_sol'] = current_value + 1

			if all(is_city):
				current_value = city_scores.get('all_sol', 0)
				city_scores['all_sol'] = current_value + 1

			countries = [item['country_code'] for item in reverse_geocode.search(ip_result)]
			is_country = [item == original_country for item in countries]

			if any(is_country):
				current_value = country_scores.get('atleast_one_sol', 0)
				country_scores['atleast_one_sol'] = current_value + 1

			if all(is_country):
				current_value = country_scores.get('atleast_one_sol', 0)
				country_scores['all_sol'] = current_value + 1

			continents = [pc.country_alpha2_to_continent_code(item) for item in countries]
			is_continent = [item == original_continent for item in continents]

			if any(is_continent):
				current_value = continent_scores.get('atleast_one_sol', 0)
				continent_scores['atleast_one_sol'] = current_value + 1

			if all(is_continent):
				current_value = continent_scores.get('all_sol', 0)
				continent_scores['all_sol'] = current_value + 1

			current_value = total_counts.get('atleast_one_sol', 0)
			total_counts['atleast_one_sol'] = current_value + 1
			total_counts['all_sol'] = current_value + 1

	print ('*' * 50)
	print ('City-level accuracies: ')
	for source, count in city_scores.items():
		print (f'{source}: {count / total_counts[source] * 100} %')

	print ('*' * 50)
	print ('Country-level accuracies: ')
	for source, count in country_scores.items():
		print (f'{source}: {count / total_counts[source] * 100} %')

	print ('*' * 50)
	print ('Continent-level accuracies: ')
	for source, count in continent_scores.items():
		print (f'{source}: {count / total_counts[source] * 100} %')



def get_percentage_correctness_overall (maxmind_ip_to_coordinates, ripe_ip_to_coordinates, caida_ip_to_coordinates, iplocation_ip_to_coordinates, overlap_ip_to_location, sol_validated_locations, threshold=50, geolocation_thresholds=[0.6], sol_thresholds=[0.05]):

	city_scores = {}
	country_scores = {}
	continent_scores = {}
	total_counts = {}

	for ip, location in overlap_ip_to_location.items():
		original_location = location
		original_country = reverse_geocode.search([original_location])[0]['country_code']
		original_continent = pc.country_alpha2_to_continent_code(original_country)

		correctness = [0] * 3
		updated = False 
		all_results = []

		ripe_location = ripe_ip_to_coordinates.get(ip, None)
		if ripe_location:
			update_correctness_dicts(ripe_location, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'ripe', correctness, threshold=50)
			update = True
			all_results.append(ripe_location)

		caida_location = caida_ip_to_coordinates.get(ip, None)
		if caida_location:
			update_correctness_dicts(caida_location, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'caida', correctness, threshold=50)
			update = True
			all_results.append(caida_location)

		maxmind_location = maxmind_ip_to_coordinates.get(ip, None)
		if maxmind_location:
			update_correctness_dicts(maxmind_location, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'maxmind', correctness, threshold=50)
			update = True
			all_results.append(maxmind_location)

		iplocation_location = iplocation_ip_to_coordinates.get(ip, None)
		if iplocation_location:
			if len(iplocation_location) != 8:
				print ('Things are bad, recheck your code')
			for index, single_iplocation in enumerate(iplocation_location):
				if single_iplocation:
					update_correctness_dicts(single_iplocation, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'iplocation_{}'.format(index), correctness, threshold=50)
					update = True
					all_results.append(single_iplocation)

		if len(all_results) > 0:
			clusters, len_list = cluster_locations(all_results)
			max_cluster = get_sorted_mean_clusters(clusters)[0]
			update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'all-max', [0] * 3, threshold=50)

		sol_validated_ip_val = sol_validated_locations.get(ip, None)
		if sol_validated_ip_val:
			location_index = sol_validated_ip_val['location_index']
			coordinates = sol_validated_ip_val['coordinates']
			for sol_threshold in sol_thresholds:
				ip_result = []
				for index, total_count in enumerate(sol_validated_ip_val['total_count']):
					if total_count > 0:
						coordinate_index = location_index.index(index)
						if (sol_validated_ip_val['penalty_count'][index] / total_count) <= sol_threshold:
							ip_result.append(coordinates[coordinate_index])

				if len(ip_result) > 0:
					clusters, len_list = cluster_locations(ip_result)
					max_cluster = get_sorted_mean_clusters(clusters)[0]
					update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'Nautilus-max-{}'.format(sol_threshold), [0] * 3, threshold=50)

					for geolocation_threshold in geolocation_thresholds:
						if max(len_list) >= geolocation_threshold:
							update_correctness_dicts(max_cluster, original_location, original_country, original_continent, city_scores, country_scores, continent_scores, total_counts, 'Nautilus-{}-{}'.format(geolocation_threshold, sol_threshold), [0] * 3, threshold=50)


	local_name_to_actual_name = {'maxmind': 'Maxmind', 'ripe': 'RIPE', 'caida': 'CAIDA', 'iplocation_0': 'IP2Location', 'iplocation_1': 'IPinfo', 'iplocation_2': 'DB-IP', 'iplocation_3': 'IPregistry',
	       'iplocation_4': 'IPGeolocation', 'iplocation_5': 'IPapi.co', 'iplocation_6': 'IPAPI', 'iplocation_7': 'IPdata', 'Nautilus-max-0.05': 'Nautilus'}


	scores = {}

	print ('*' * 50)
	print ('City-level accuracies: ')
	for source, count in city_scores.items():
		print (f'{source}: {round(count / len(overlap_ip_to_location) * 100, 2)} %')
		print (f'{source} total count: {total_counts[source]}')
		print (f'{source} total count %age : {total_counts[source]/len(ip_to_location)*100}')
		if source in local_name_to_actual_name:
			scores[local_name_to_actual_name[source]] = [round(count / len(overlap_ip_to_location) * 100, 2)]

	print ('*' * 50)
	print ('Country-level accuracies: ')
	for source, count in country_scores.items():
		print (f'{source}: {round(count / len(overlap_ip_to_location) * 100, 2)} %')
		if source in local_name_to_actual_name:
			scores[local_name_to_actual_name[source]].append(round(count / len(overlap_ip_to_location) * 100, 2))

	print ('*' * 50)
	print ('Continent-level accuracies: ')
	for source, count in continent_scores.items():
		print (f'{source}: {round(count / len(overlap_ip_to_location) * 100, 2)} %')
		if source in local_name_to_actual_name:
			scores[local_name_to_actual_name[source]].append(round(count / len(overlap_ip_to_location) * 100, 2))

	scores = {k:v for k,v in sorted(scores.items(), key=lambda x: x[1][0])}

	with open('plot_results/geolocation_accuracies.dat', 'w') as fp:
		string = 'N N ' + ' '.join(scores.keys())
		fp.write(string+'\n')
		string = '1 City ' + ' '.join([str(item[0]) for item in scores.values()])
		fp.write(string+'\n')
		string = '2 Country ' + ' '.join([str(item[1]) for item in scores.values()])
		fp.write(string+'\n')
		string = '3 Continent ' + ' '.join([str(item[2]) for item in scores.values()])
		fp.write(string+'\n')



if __name__ == '__main__':

	ip_to_location = load_and_process_ground_truth_data()
	maxmind_distances, ripe_distances, caida_distances, iplocation_distances, maxmind_ip_to_coordinates, ripe_ip_to_coordinates, caida_ip_to_coordinates, iplocation_ip_to_coordinates = process_results_from_all_sources(ip_to_location)
	overlap_ip_to_location, sol_validated_locations = get_overlap_with_sol_validated(ip_to_location)
	get_percentage_correctness_overall(maxmind_ip_to_coordinates, ripe_ip_to_coordinates, caida_ip_to_coordinates, iplocation_ip_to_coordinates, overlap_ip_to_location, sol_validated_locations, threshold=50, geolocation_thresholds=[0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85], sol_thresholds=[0.05, 0.03, 0.01, 0])