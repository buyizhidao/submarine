import pickle, json, itertools
from collections import namedtuple
from pathlib import Path

import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

from utils.merge_data import common_merge_operation, save_results_to_file
from utils.traceroute_utils import load_all_links_and_ips_data
from utils.pickle_compat import load_pickle

from sklearn.cluster import DBSCAN
import numpy as np
from sklearn.neighbors import BallTree

import pycountry
import pycountry_convert as pc

import requests
from bs4 import BeautifulSoup

import reverse_geocode
from collections import Counter

import geopandas as gpd
from itertools import product
from collections.abc import Iterable

# Later update these 2 to directly take from geolocation files (under location/)
Location = namedtuple('Location', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network', 'ISP', 'Org'])
MaxmindLocation = namedtuple('MaxmindLocation', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network'])
LandingPoints = namedtuple('LandingPoints', ['latitude', 'longitude', 'country', 'location', 'cable'])


def _load_pickle_first_existing(file_locations, required=True):
	for file_location in file_locations:
		if Path(file_location).exists():
			with open(file_location, 'rb') as fp:
				return pickle.load(fp)
	if required:
		raise FileNotFoundError('None of these files exist: {}'.format(', '.join(file_locations)))
	return {}


def load_all_geolocation_sources(ip_version=4, tags='default', geo_source_mode='all'):

 # Loading data from all geolocation sources

	directory = str(output_path('location_data'))

	try:
		if geo_source_mode == 'maxmind_only':
			maxmind_location_dict = _load_pickle_first_existing([
			 '{}/maxmind_location_output_v{}_{}'.format(directory, ip_version, tags),
			 '{}/maxmind_location_ouput_v{}_{}'.format(directory, ip_version, tags),
			])
			print (f'From Maxmind/DB-IP, we got results for {len(maxmind_location_dict)} IPs')
			return ({}, {}, maxmind_location_dict, {})

		ripe_location_dict = _load_pickle_first_existing([
		 '{}/ripe_location_output_v{}_{}'.format(directory, ip_version, tags),
		 '{}/ripe_location_ouput_v{}_{}'.format(directory, ip_version, tags),
		])

		print (f'From RIPE, we got result for {len(ripe_location_dict)} IPs')

		if ip_version == 4:
			caida_location_dict = _load_pickle_first_existing([
			 '{}/caida_location_output_v{}_{}'.format(directory, ip_version, tags),
			 '{}/caida_location_ouput_v{}_{}'.format(directory, ip_version, tags),
			 '{}/caida_location_output_{}'.format(directory, tags),
			])
		else:
			caida_location_dict = {}

		print (f'From CAIDA, we got results for {len(caida_location_dict)} IPs')

		maxmind_location_dict = _load_pickle_first_existing([
		 '{}/maxmind_location_output_v{}_{}'.format(directory, ip_version, tags),
		 '{}/maxmind_location_ouput_v{}_{}'.format(directory, ip_version, tags),
		])

		print (f'From Maxmind, we got results for {len(maxmind_location_dict)} IPs')

		iplocation_dict = _load_pickle_first_existing([
		 '{}/iplocation_location_output_v{}_{}'.format(directory, ip_version, tags),
		 '{}/iplocation_location_ouput_v{}_{}'.format(directory, ip_version, tags),
		])

		print (f'From IPlocation, we got results for {len(iplocation_dict)} IPs')

		return (ripe_location_dict, caida_location_dict, maxmind_location_dict, iplocation_dict)

	except Exception as e:

		print (f'Most likely the required files were not generated. We got the error: {str(e)}')
		sys.exit(1)



def load_sol_validated_file(ip_version=4):

 # If SoL validation is done, we can eliminate some of the incorrect location sources

	directory = str(output_path('location_data'))

	file = f'{directory}/all_validated_ip_location_v{ip_version}'

	result = None

	if not Path(file).exists():
		result = common_merge_operation(str(output_path('location_data')), 0, [], [f'validated_ip_locations_v{ip_version}'], True, f'all_validated_ip_location_v{ip_version}')
	else:
		print (f'Directly loading the saved SoL file from all sources')
		with open(file, 'rb') as fp:
			result = pickle.load(fp)

	if result:
		return result
	else:
		print ('Run the SoL validation while collecting traceroutes')
		sys.exit(1)



def load_all_probe_ip_to_locations(required=True):

 # Unfortunately for CAIDA our source does not provide IPs for anchors (maybe a future work)
 # Let's utilize RIPE data
	ripe_probe_file = str(output_path('all_ripe_probes_ip_and_coordinates'))

	if Path(ripe_probe_file).exists():
		with open(ripe_probe_file, 'rb') as fp:
			ripe_probe_map = pickle.load(fp)

		ripe_ip_to_location_dict = {v[0]: [v[1]] for v in ripe_probe_map.values()}
		return ripe_ip_to_location_dict

	else:
		if required:
			print (f'Generate RIPE probe map files')
			sys.exit(1)
		return {}



def get_latitude_longitude_info_for_all_ips_only_geolocation_sources (all_ips, ripe_location_dict, caida_location_dict, maxmind_location_dict, iplocation_dict):

	ip_to_latlon_dict = {}

	ripe_missed, maxmind_missed, iplocation_missed = 0, 0, [0] * 8

	for ip in all_ips:
		ip_result = []

		ripe_val = ripe_location_dict.get(ip, None)
		if ripe_val:
			try:
				ripe_latlon = (float(ripe_val[-3]), float(ripe_val[-2]))
				ip_result.append(ripe_latlon)
			except:
				ripe_missed += 1
				pass

		caida_val = caida_location_dict.get(ip, None)
		if caida_val:
			caida_latlon = (float(caida_val[-3]), float(caida_val[-2]))
			ip_result.append(caida_latlon)

		maxmind_val = maxmind_location_dict.get(ip, None)
		if maxmind_val:
			try:
				maxmind_latlon = (float(maxmind_val.latitude), float(maxmind_val.longitude))
				ip_result.append(maxmind_latlon)
			except:
				maxmind_missed += 1
				pass

		iplocation_val = iplocation_dict.get(ip, None)
		if iplocation_val:
			for index, item in enumerate(iplocation_val):
				try:
					iplocation_latlon = (float(item.latitude.decode()), float(item.longitude.decode()))
					ip_result.append(iplocation_latlon)
				except:
					iplocation_missed[index] += 1
					pass

		if len(ip_result) > 0:
			ip_to_latlon_dict[ip] = ip_result


	print (f'Due to errors, we missed \n\t{ripe_missed} IPs from RIPE\n\t{maxmind_missed} IPs from Maxmind\n\t{iplocation_missed} IPs from IPlocation')

	print (f'Finally, we have results for {len(ip_to_latlon_dict)} IPs')

	return ip_to_latlon_dict



def get_latitude_longitude_info_for_all_ips_sol_validated (all_ips, sol_validated_result, threshold=0.01):

	ip_to_latlon_dict = {}
	ip_to_latlon_dict_negative = {}

	for ip in all_ips:
  
		sol_validated_ip_val = sol_validated_result.get(ip, None)
		ip_result = []
		ip_result_negative = []

		if sol_validated_ip_val:
			location_index = sol_validated_ip_val['location_index']
			coordinates = sol_validated_ip_val['coordinates']
			for index, total_count in enumerate(sol_validated_ip_val['total_count']):
    
			 # Checking if we got any location info from this geolocation service
				if total_count > 0:
     
				 # Getting the index for the coordinate list
					coordinate_index = location_index.index(index)
     
					# Checking if it satisfies the SoL threshold check
					if (sol_validated_ip_val['penalty_count'][index] / total_count) <= threshold:
						ip_result.append(coordinates[coordinate_index])

					else:
						ip_result_negative.append(coordinates[coordinate_index])

		if len(ip_result) > 0:
			ip_to_latlon_dict[ip] = ip_result
		else:
		 # Just in case all sources are bad, let's consider anyway and assign some huge penalty
			if len(ip_result_negative) > 0:
				ip_to_latlon_dict_negative[ip] = ip_result_negative


	print (f'We have results for {len(ip_to_latlon_dict)} IPs where atleast 1 source has satisifed SoL constraints')
	print (f'There are {len(ip_to_latlon_dict_negative)} IPs for which no source satisifed SoL constraints')

	return ip_to_latlon_dict, ip_to_latlon_dict_negative



def get_latitude_longitude_info_for_all_ips (all_ips, ip_version=4, mode=2, threshold=0.01, geo_source_mode='maxmind_only'):

 # Modes 0 -> only geolocation sources, 1 -> only SoL validated, 2 -> both

	ripe_ip_to_location_dict = load_all_probe_ip_to_locations(required=(geo_source_mode != 'maxmind_only'))

	ip_to_latlon_dict_geolocation, ip_to_latlon_dict_sol, ip_to_latlon_dict_negative_sol = {}, {}, {}

	if mode in [0, 2]:
  
		ripe_location_dict, caida_location_dict, maxmind_location_dict, iplocation_dict = load_all_geolocation_sources(ip_version, geo_source_mode=geo_source_mode)
		ip_to_latlon_dict_geolocation = get_latitude_longitude_info_for_all_ips_only_geolocation_sources (all_ips, ripe_location_dict, caida_location_dict, maxmind_location_dict, iplocation_dict)

		# Deleting processed sources to save memory
		del(ripe_location_dict)
		del(caida_location_dict)
		del(maxmind_location_dict)
		del(iplocation_dict)

		# Irrespective of the source, lets make the probe locations to be as seen from original RIPE probe data
		ip_to_latlon_dict_geolocation.update(ripe_ip_to_location_dict)

	if mode in [1, 2]:

		sol_validated_result = load_sol_validated_file(ip_version)
		ip_to_latlon_dict_sol, ip_to_latlon_dict_negative_sol = get_latitude_longitude_info_for_all_ips_sol_validated (all_ips, sol_validated_result, threshold)

		# Deleting processed sources to save memory
		del(sol_validated_result)

		ip_to_latlon_dict_sol.update(ripe_ip_to_location_dict)

		overlap_with_negative = set(ip_to_latlon_dict_negative_sol.keys()) & set(ripe_ip_to_location_dict.keys())

		print (f'We had an overlap of {len(overlap_with_negative)} IPs and original probes count is {len(ripe_ip_to_location_dict)}')


	return ip_to_latlon_dict_geolocation, ip_to_latlon_dict_sol, ip_to_latlon_dict_negative_sol



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


def get_sorted_mean_clusters (cluster):
    return [list(item) for item in list(map(lambda p: np.mean(p, axis=0), sorted(cluster, key=len, reverse=True)))]


def cluster_locations(locations_list):
    cluster = DBSCAN(eps=100/6371., min_samples = 1, algorithm='ball_tree', metric='haversine', leaf_size=2).fit_predict(np.radians(locations_list))
    return get_cluster_as_list(cluster, locations_list)



def generate_latlon_cluster_and_score_map (all_ips, ip_version=4, mode=2, threshold=0.01, geo_source_mode='maxmind_only'):

	geolocation_latlon_cluster_and_score_map = {}
	geolocation_latlon_cluster_and_score_map_sol_validated = {}

	save_directory = output_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

 
	# This is if we want individual sources
	if mode in [0, 2]:

		save_file = 'geolocation_latlon_cluster_and_score_map_v{}'.format(ip_version)

		if Path(save_directory / save_file).is_file():
   
			print (f'Directly loading the saved file contents')
			with open(save_directory / save_file, 'rb') as fp:
				geolocation_latlon_cluster_and_score_map = pickle.load(fp)
   
		else:

			ip_to_latlon_dict_geolocation, _, _ = get_latitude_longitude_info_for_all_ips(all_ips, ip_version, 0, threshold, geo_source_mode=geo_source_mode)

			if len(ip_to_latlon_dict_geolocation) > 0:

				for count, ip in enumerate(all_ips):
					locations_list = ip_to_latlon_dict_geolocation.get(ip, None)
					if locations_list:
						con_cluster, len_cluster = cluster_locations(locations_list)
						geolocation_latlon_cluster_and_score_map[ip] = (con_cluster, len_cluster, 0)

				if len(geolocation_latlon_cluster_and_score_map) > 0:
					print (f'We have clusters and scores (geolocation) for {len(geolocation_latlon_cluster_and_score_map)} IPs')
					save_results_to_file(geolocation_latlon_cluster_and_score_map, str(save_directory), save_file)

    # Deleting finished ones to save memory
				del(ip_to_latlon_dict_geolocation)

 # This is if we want SoL validated results
	if mode in [1, 2]:

		save_file = 'geolocation_latlon_cluster_and_score_map_sol_validated_v{}'.format(ip_version)

		if Path(save_directory / save_file).is_file():

			print (f'Directly loading the saved file contents')
			with open(save_directory / save_file, 'rb') as fp:
				geolocation_latlon_cluster_and_score_map_sol_validated = pickle.load(fp)
  
		else:

			_, ip_to_latlon_dict_sol, ip_to_latlon_dict_negative_sol =  get_latitude_longitude_info_for_all_ips(all_ips, ip_version, 1, threshold, geo_source_mode=geo_source_mode)

			if len(ip_to_latlon_dict_sol) > 0:

				for count, ip in enumerate(all_ips):
					locations_list = ip_to_latlon_dict_sol.get(ip, None)
					if locations_list:
						con_cluster, len_cluster = cluster_locations(locations_list)
						geolocation_latlon_cluster_and_score_map_sol_validated[ip] = (con_cluster, len_cluster, 0)
					else:
					 # Maybe none of the sources had good geolocation, let's get from the bad ones and add a penalty later
						locations_list = ip_to_latlon_dict_negative_sol.get(ip, None)
						if locations_list:
							con_cluster, len_cluster = cluster_locations(locations_list)
							geolocation_latlon_cluster_and_score_map_sol_validated[ip] = (con_cluster, len_cluster, 1)

				if len(geolocation_latlon_cluster_and_score_map_sol_validated) > 0:
					print (f'We have clusters and scores (SoL) for {len(geolocation_latlon_cluster_and_score_map_sol_validated)} IPs')
					save_results_to_file(geolocation_latlon_cluster_and_score_map_sol_validated, str(save_directory), save_file)

    # Deleting finished variables to save memory
				del(ip_to_latlon_dict_sol)
				del(ip_to_latlon_dict_negative_sol)


	return geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated



def generate_initial_category_mapping_for_geolocation (links, geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, mode=2, geolocation_threshold=0.6, ignore=True):

 # We will use ignore to decide whether to include links where one end has not passed any SoL testing

	ip_geolocation_category = {}
	skipped_links = 0
	ip_geolocation_category_sol_validated = {}
	skipped_links_sol_validated = 0

	for ip_address_1, ip_address_2 in links:

		link = (ip_address_1, ip_address_2)

		if mode in [0, 2]:
			ip_location_1 = geolocation_latlon_cluster_and_score_map.get(ip_address_1, None)
			ip_location_2 = geolocation_latlon_cluster_and_score_map.get(ip_address_2, None)

			if ip_location_1 and ip_location_2:
				score_location_1 = max(ip_location_1[1])
				score_location_2 = max(ip_location_2[1])

				if score_location_1 >= geolocation_threshold and score_location_2 >= geolocation_threshold:
					ip_geolocation_category[link] = 'bg'
				elif (score_location_1 >= geolocation_threshold and score_location_2 < geolocation_threshold) or\
      (score_location_1 < geolocation_threshold and score_location_2 >= geolocation_threshold):
					ip_geolocation_category[link] = 'og'
				else:
					ip_geolocation_category[link] = 'bb'
			else:
				skipped_links += 1

   

		if mode in [1, 2]:
			ip_location_1 = geolocation_latlon_cluster_and_score_map_sol_validated.get(ip_address_1, None)
			ip_location_2 = geolocation_latlon_cluster_and_score_map_sol_validated.get(ip_address_2, None)

			if ip_location_1 and ip_location_2:
				score_location_1 = max(ip_location_1[1])
				score_location_2 = max(ip_location_2[1])

				if ignore:
					if ip_location_1[2] == 0 and ip_location_2[2] == 0:
						if score_location_1 >= geolocation_threshold and score_location_2 >= geolocation_threshold:
							ip_geolocation_category_sol_validated[link] = 'bg'
						elif (score_location_1 >= geolocation_threshold and score_location_2 < geolocation_threshold) or\
        (score_location_1 < geolocation_threshold and score_location_2 >= geolocation_threshold):
							ip_geolocation_category_sol_validated[link] = 'og'
						else:
							ip_geolocation_category_sol_validated[link] = 'bb'
					else:
						skipped_links_sol_validated += 1
			else:
				skipped_links_sol_validated += 1

   
	print (f'Only Geolocation: Skipped {skipped_links} links and got results for {len(ip_geolocation_category)} links')

	print (f"Both ends good geolocation are {list(ip_geolocation_category.values()).count('bg')} and \
				\nOne end good geolocation are {list(ip_geolocation_category.values()).count('og')} and \
				\nBoth ends bad geolocation are {list(ip_geolocation_category.values()).count('bb')}")

	print (f'SoL: Skipped {skipped_links_sol_validated} links and got results for {len(ip_geolocation_category_sol_validated)} links')

	print (f"Both ends good geolocation are {list(ip_geolocation_category_sol_validated.values()).count('bg')} and \
				\nOne end good geolocation are {list(ip_geolocation_category_sol_validated.values()).count('og')} and \
				\nBoth ends bad geolocation are {list(ip_geolocation_category_sol_validated.values()).count('bb')}")


	return ip_geolocation_category, ip_geolocation_category_sol_validated


def get_country_to_continent_map():

 # Some initial list of countries for which match was not found
	country_to_continent_map = {'732': 'AF', '612': 'OC', '534': 'NA', '626': 'AS', '581': 'NA', '336': 'EU', 
	       '412': 'EU', '158': 'AS', '553': 'SA', '485': 'OC', '654': 'AF', '010': 'AN', '260': 'AN'}

	for country in pycountry.countries:
		try:
			country_to_continent_map[country.numeric] = pc.country_alpha2_to_continent_code(country.alpha_2)
		except:
			pass

	return country_to_continent_map



def get_country_alpha_to_digit():

	country_file = raw_path('iso3166-countrycodes.txt')

	with open(country_file) as f:
	    file_content = f.readlines()
     
	country_2alpha_to_digit = {'AX': '248', 'XK': '412', 'PM': '666', 'SH': '654'}

	res = ''
	for country in file_content[12:]:
	    a = [' '.join(item.strip().split(', ')[::-1]) for item in country.split('\t') if item.strip() != '']
	    if len(a) != 4:
	        a = [' '.join(item.strip().split(', ')[::-1]) for item in a[0].split('  ') if item.strip() != '']
	        if len(a) != 4:
	            res = a[-1]
	    else:
	        a[0] = (res + ' ' + a[0]).strip()
	        country_2alpha_to_digit[a[1]] = a[-1]
	        res = ''

	return country_2alpha_to_digit



def get_country_continent_helper (dictionary, country_to_continent_map, country_2alpha_to_digit):

	count = 0
	verbose = True

	country_result, continent_result = {}, {}

	for ip, value in dictionary.items():
  
		all_coordinates = [i for item in value[0] for i in item]
		reverse_geocode_result = reverse_geocode.search(all_coordinates)
  
		countries = [country_2alpha_to_digit[item['country_code']] for item in reverse_geocode_result]
		count_of_countries = len(countries)
		counter = Counter(countries)
		country_result[ip] = [tuple(counter.keys()), tuple([item/count_of_countries for item in counter.values()])]

		continents = [country_to_continent_map[item] for item in countries]
		count_of_continents = len(continents)
		counter = Counter(continents)

		continent_result[ip] = [tuple(counter.keys()), tuple([item/count_of_continents for item in counter.values()])]

		if count % 10000 == 0 and verbose:
			print (f'Completed for {count} queries')

		count += 1

	return country_result, continent_result



def get_country_and_continent_clusters_for_all_ips (all_ips, ip_version=4, mode=2, sol_threshold=0.01):

	country_to_continent_map = get_country_to_continent_map()
	country_2alpha_to_digit = get_country_alpha_to_digit()

	geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated = generate_latlon_cluster_and_score_map (all_ips, ip_version, mode, sol_threshold)

	save_directory = output_path('mapping_outputs')

	geolocation_country_cluster, geolocation_continent_cluster = {}, {}
	geolocation_country_cluster_sol_validated, geolocation_continent_cluster_sol_validated = {}, {}

	if mode in [0, 2]:

		save_file_country = 'geolocation_country_cluster_v{}'.format(ip_version)

		if Path(save_directory / save_file_country).is_file():
   
			print (f'Directly loading the saved file contents')
			with open(save_directory / save_file_country, 'rb') as fp:
				geolocation_country_cluster = pickle.load(fp)

		save_file_continent = 'geolocation_continent_cluster_v{}'.format(ip_version)

		if Path(save_directory / save_file_continent).is_file():
   
			print (f'Directly loading the saved file contents')
			with open(save_directory / save_file_continent, 'rb') as fp:
				geolocation_continent_cluster = pickle.load(fp)

		if len(geolocation_country_cluster) == 0 or len(geolocation_continent_cluster) == 0:

			geolocation_country_cluster, geolocation_continent_cluster = get_country_continent_helper(geolocation_latlon_cluster_and_score_map, country_to_continent_map, country_2alpha_to_digit)

			save_results_to_file(geolocation_country_cluster, str(save_directory), save_file_country)
			save_results_to_file(geolocation_continent_cluster, str(save_directory), save_file_continent)

	if mode in [1, 2]:

		save_file_country = 'geolocation_country_cluster_sol_validated_v{}'.format(ip_version)

		if Path(save_directory / save_file_country).is_file():
   
			print (f'Directly loading the saved file contents')
			with open(save_directory / save_file_country, 'rb') as fp:
				geolocation_country_cluster_sol_validated = pickle.load(fp)

		save_file_continent = 'geolocation_continent_cluster_sol_validated_v{}'.format(ip_version)

		if Path(save_directory / save_file_continent).is_file():
   
			print (f'Directly loading the saved file contents')
			with open(save_directory / save_file_continent, 'rb') as fp:
				geolocation_continent_cluster_sol_validated = pickle.load(fp)

		if len(geolocation_country_cluster_sol_validated) == 0 or len(geolocation_continent_cluster_sol_validated) == 0:

			geolocation_country_cluster_sol_validated, geolocation_continent_cluster_sol_validated = get_country_continent_helper(geolocation_latlon_cluster_and_score_map_sol_validated, country_to_continent_map, country_2alpha_to_digit)

			save_results_to_file(geolocation_country_cluster_sol_validated, str(save_directory), save_file_country)
			save_results_to_file(geolocation_continent_cluster_sol_validated, str(save_directory), save_file_continent)


	return geolocation_country_cluster, geolocation_continent_cluster, geolocation_country_cluster_sol_validated, geolocation_continent_cluster_sol_validated
   


def load_shp_file(file):
	return gpd.read_file(file)



def get_neighbors_for_countries(gdf):
    
	gdf["NEIGHBORS"] = None  

	for index, country in gdf.iterrows():   

	    # get 'not disjoint' countries
	    neighbors = gdf[~gdf.geometry.disjoint(country.geometry)].CNTRY_CODE.tolist()

	    # remove own name of the country from the list
	    neighbors = [ name for name in neighbors if country.CNTRY_CODE != name ]

	    # add names of neighbors as NEIGHBORS value
	    gdf.at[index, "NEIGHBORS"] = '; '.join(neighbors)
     
	return gdf



def save_shp_file(gdf, file):
	return gdf.to_file(file)



def generate_gdf_dict():

	shp_file_location = raw_path('IPUMSI_world_release2020/world_countries_2020.shp')
	save_file_location = output_path('mapping_outputs/country_neighbors_as_3digit_codes')

	if Path(save_file_location).exists():
		print ('Directly loading from the saved file')
		result_gdf = load_shp_file(str(save_file_location))
		gdf_dict = result_gdf.to_dict()

	else:
		if Path(shp_file_location).exists():
			gdf = load_shp_file(str(shp_file_location))
			updated_gdf = get_neighbors_for_countries(gdf) 

			# Let's save for future use
			save_shp_file(updated_gdf, str(save_file_location))
			gdf_dict = updated_gdf.to_dict()

		else:
			print (f'Download IPUMSI data at "https://international.ipums.org/international/resources/gis/IPUMSI_world_release2020.zip" and save the unzipped folder in the data/intermediate directory')
			sys.exit(1)

	return gdf_dict



def flatten(lis):
	for item in lis:
		if isinstance(item, Iterable) and not isinstance(item, str):
		    for x in flatten(item):
		        yield x
		else:        
			yield item



def index_to_country_code_map_gdf (gdf_dict):
	return {k:v for v,k in gdf_dict['CNTRY_CODE'].items()}



def get_index_for_country_code_in_gdf (countries_list, index_to_country_code_map):
	country_code_to_index_map = []
	for country in countries_list:
		index = index_to_country_code_map.get(country, None)
		country_code_to_index_map.append(index)
	return country_code_to_index_map



def get_neighbor_for_given_country_index(gdf_dict, index_list):
	neighbors_list = []
	for item in index_list:
		if item:
			if gdf_dict['NEIGHBORS'][item]:
				neighbors = gdf_dict['NEIGHBORS'][item].split('; ')
			else:
				neighbors = None
			neighbors_list.append(neighbors)

	return neighbors_list



def get_neighbors_for_given_country_list(gdf_dict, country_list, index_to_country_code_map):
	indices = get_index_for_country_code_in_gdf(country_list, index_to_country_code_map)
	return get_neighbor_for_given_country_index(gdf_dict, indices)



def get_iterative_neighbors (gdf_dict, country_list, index_to_country_code_map, level=2):
	init_level = 0
	all_neighbors = {}
	for country in list(country_list):
		processed = []
		countries_to_process = [country]
		country_neighbors = [country]
		while init_level < level:
			if len(countries_to_process) == 0:
				break
			neighbors = get_neighbors_for_given_country_list(gdf_dict, countries_to_process, index_to_country_code_map)
			processed.extend(countries_to_process)
			country_neighbors.extend(list(flatten(neighbors)))
			init_level += 1
			countries_to_process = [con for con in list(set(processed) ^ set(country_neighbors)) if con != None]
		all_neighbors[country] = list(set(country_neighbors))
		init_level = 0

	return all_neighbors



def generate_category_mapping_based_on_continent_data (links, geolocation_continent_cluster, geolocation_continent_cluster_sol_validated, mode=2):

	ip_is_oceanic_cable_continent_based = {}
	skipped_links = 0
	ip_is_oceanic_cable_continent_based_sol_validated = {}
	skipped_links_sol_validated = 0

	submarine_cable_possibilities = {('AS', 'NA'), ('AS', 'SA'), ('AS', 'OC'), 
	                                ('NA', 'AS'), ('NA', 'SA'), ('NA', 'OC'), ('NA', 'EU'), ('NA', 'AF'),
	                                ('SA', 'AS'), ('SA', 'NA'), ('SA', 'OC'), ('SA', 'EU'), ('SA', 'AF'),
	                                ('OC', 'AS'), ('OC', 'NA'), ('OC', 'SA'), ('OC', 'EU'), ('OC', 'AF'),
	                                ('EU', 'NA'), ('EU', 'SA'), ('EU', 'OC'),
	                                ('AF', 'NA'), ('AF', 'SA'), ('AF', 'OC')}

	for ip_address_1, ip_address_2 in links:

		link = (ip_address_1, ip_address_2)

		if mode in [0, 2]:
			ip_con_1 = geolocation_continent_cluster.get(ip_address_1, None)
			ip_con_2 = geolocation_continent_cluster.get(ip_address_2, None)

			if ip_con_1 and ip_con_2:
				oc_val = 'oc'
				combinations = list(product(ip_con_1[0], ip_con_2[0]))
				unique_combinations = list(set([tuple(set(item)) for item in combinations]))
				for combination in unique_combinations:
					if len(combination) == 1:
						oc_val = 'te'
						break
					else:
						if combination not in submarine_cable_possibilities:
							oc_val = 'te'
							break
				ip_is_oceanic_cable_continent_based[link] = oc_val
			else:
				skipped_links += 1

   
		if mode in [1, 2]:
			ip_con_1 = geolocation_continent_cluster_sol_validated.get(ip_address_1, None)
			ip_con_2 = geolocation_continent_cluster_sol_validated.get(ip_address_2, None)

			if ip_con_1 and ip_con_2:
				oc_val = 'oc'
				combinations = list(product(ip_con_1[0], ip_con_2[0]))
				unique_combinations = list(set([tuple(set(item)) for item in combinations]))
				for combination in unique_combinations:
					if len(combination) == 1:
						oc_val = 'te'
						break
					else:
						if combination not in submarine_cable_possibilities:
							oc_val = 'te'
							break
				ip_is_oceanic_cable_continent_based_sol_validated[link] = oc_val
			else:
				skipped_links_sol_validated += 1

   
	print (f'Only geolocation: Skipped {skipped_links} links and got results for {len(ip_is_oceanic_cable_continent_based)} links')
	print (f"Based on continent mapping, we got {list(ip_is_oceanic_cable_continent_based.values()).count('oc')} definite submarine and {list(ip_is_oceanic_cable_continent_based.values()).count('te')} potential terrestrial")

	print (f'SoL: Skipped {skipped_links_sol_validated} links and got results for {len(ip_is_oceanic_cable_continent_based_sol_validated)} links')
	print (f"Based on continent mapping, we got {list(ip_is_oceanic_cable_continent_based_sol_validated.values()).count('oc')} definite submarine and {list(ip_is_oceanic_cable_continent_based_sol_validated.values()).count('te')} potential terrestrial")

	return ip_is_oceanic_cable_continent_based, ip_is_oceanic_cable_continent_based_sol_validated



def generate_category_mapping_based_on_neighbors_data (links, geolocation_country_cluster, geolocation_country_cluster_sol_validated, mode=2):

	ip_is_oceanic_cable_neighbor_based = {}
	skipped_links = 0
	ip_is_oceanic_cable_neighbor_based_sol_validated = {}
	skipped_links_sol_validated = 0

	verbose = True
	count = 0

	gdf_dict = generate_gdf_dict()
	index_to_country_code_map = index_to_country_code_map_gdf(gdf_dict)

	for ip_address_1, ip_address_2 in links:

		link = (ip_address_1, ip_address_2)

		if mode in [0, 2]:
			ip_country_1 = geolocation_country_cluster.get(ip_address_1, None)
			ip_country_2 = geolocation_country_cluster.get(ip_address_2, None)

			oc_val = 'oc'
			if ip_country_1 and ip_country_2:
			 # Let's always find the neighbors for ip_address_1 and check if the country for ip_address_2 falls in the neighbors
				neighbors = get_iterative_neighbors(gdf_dict, ip_country_1[0], index_to_country_code_map)
				combinations = list(product(ip_country_1[0], ip_country_2[0]))
				for combination in combinations:
					if combination[1] in neighbors[combination[0]]:
						oc_val = 'te'
						break
				ip_is_oceanic_cable_neighbor_based[link] = oc_val
			else:
				skipped_links += 1

   
		if mode in [1, 2]:
			ip_country_1 = geolocation_country_cluster_sol_validated.get(ip_address_1, None)
			ip_country_2 = geolocation_country_cluster_sol_validated.get(ip_address_2, None)

			oc_val = 'oc'
			if ip_country_1 and ip_country_2:
			 # Let's always find the neighbors for ip_address_1 and check if the country for ip_address_2 falls in the neighbors
				neighbors = get_iterative_neighbors(gdf_dict, ip_country_1[0], index_to_country_code_map)
				combinations = list(product(ip_country_1[0], ip_country_2[0]))
				for combination in combinations:
					if combination[1] in neighbors[combination[0]]:
						oc_val = 'te'
						break
				ip_is_oceanic_cable_neighbor_based_sol_validated[link] = oc_val
			else:
				skipped_links_sol_validated += 1

		count += 1

   
	print (f'Only geolocation: Skipped {skipped_links} links and got results for {len(ip_is_oceanic_cable_neighbor_based)} links')
	print (f"Based on neighbor mapping, we got {list(ip_is_oceanic_cable_neighbor_based.values()).count('oc')} definite submarine and {list(ip_is_oceanic_cable_neighbor_based.values()).count('te')} potential terrestrial")

	print (f'SoL: Skipped {skipped_links_sol_validated} links and got results for {len(ip_is_oceanic_cable_neighbor_based_sol_validated)} links')
	print (f"Based on neighbor mapping, we got {list(ip_is_oceanic_cable_neighbor_based_sol_validated.values()).count('oc')} definite submarine and {list(ip_is_oceanic_cable_neighbor_based_sol_validated.values()).count('te')} potential terrestrial")

	return ip_is_oceanic_cable_neighbor_based, ip_is_oceanic_cable_neighbor_based_sol_validated



def get_countries_with_submarine_landing_points():

 # Rather than taking the country here, let's generate the countries based on reverse
 # geocode like we did with the IP location sources to maintain standard results
 
	submarine_countries = set()
	country_2alpha_to_digit = get_country_alpha_to_digit()

	with open(str(raw_path('submarine_data/landing_points_dict')), 'rb') as fp:
		landing_points = load_pickle(fp)

	for landing_point in landing_points.values():
		coordinate = (landing_point.latitude, landing_point.longitude)
		result = reverse_geocode.search([coordinate])
		country_3digit = country_2alpha_to_digit[result[0]['country_code']]
		submarine_countries.add(country_3digit)

	return list(submarine_countries)



def check_country_with_landing_points (country_list, submarine_countries):

	return all([country not in submarine_countries for country in country_list])



def generate_categories (all_ips, links, geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, ip_version=4, mode=2, sol_threshold=0.01, geolocation_threshold=0.6, ignore=True):

	categories_map = { 
	     'bg_oc': [], 'og_oc': [], 'bb_oc': [],
	     'bg_te': [], 'og_te': [], 'bb_te': [],
	     'de_te': [] 
	    }

	categories_map_sol_validated =  {
	     'bg_oc': [], 'og_oc': [], 'bb_oc': [],
	     'bg_te': [], 'og_te': [], 'bb_te': [],
	     'de_te': [] 
	    }

	save_directory = output_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	if mode in [0, 2]:
		save_file = 'categories_map_v{}'.format(ip_version)
		if Path(save_directory/save_file).exists():
			print (f'Directly loading the contents')
			with open(save_directory/save_file, 'rb') as fp:
				categories_map = pickle.load(fp)
   
			if mode == 0:
				mode = -1
			else:
				mode = 1

	if mode in [1, 2]:
		save_file = 'categories_map_sol_validated_v{}'.format(ip_version)
		if Path(save_directory/save_file).exists():
			print (f'Directly loading the contents')
			with open(save_directory/save_file, 'rb') as fp:
				categories_map_sol_validated = pickle.load(fp)
   
			if mode == 1:
				mode = -1
			else:
				mode = 0


 
	if mode != -1:

		ip_geolocation_category, ip_geolocation_category_sol_validated = generate_initial_category_mapping_for_geolocation (links, geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, mode=mode, geolocation_threshold=geolocation_threshold, ignore=ignore)

		geolocation_country_cluster, geolocation_continent_cluster, geolocation_country_cluster_sol_validated, geolocation_continent_cluster_sol_validated = get_country_and_continent_clusters_for_all_ips (all_ips, ip_version, mode, sol_threshold)

		submarine_countries = get_countries_with_submarine_landing_points()

		ip_is_oceanic_cable_continent_based, ip_is_oceanic_cable_continent_based_sol_validated = generate_category_mapping_based_on_continent_data(links, geolocation_continent_cluster, geolocation_continent_cluster_sol_validated, mode)

		ip_is_oceanic_cable_neighbor_based, ip_is_oceanic_cable_neighbor_based_sol_validated = generate_category_mapping_based_on_neighbors_data(links, geolocation_country_cluster, geolocation_country_cluster_sol_validated, mode)

  
		if mode in [0, 2]:

			save_file = 'categories_map_v{}'.format(ip_version)

			if Path(save_directory / save_file).is_file():

				print (f'Directly loading the saved file contents')
				with open(save_directory / save_file, 'rb') as fp:
					categories_map = pickle.load(fp)

				if mode == 0:
					mode = -1
				else:
					mode = 1

		if mode in [1, 2]:

			save_file = 'categories_map_sol_validated_v{}'.format(ip_version)

			if Path(save_directory / save_file).is_file():

				print (f'Directly loading the saved file contents')
				with open(save_directory / save_file, 'rb') as fp:
					categories_map_sol_validated = pickle.load(fp)

				if mode == 1:
					mode = -1
				else:
					mode = 0

		print (f'Currently in mode {mode}')

		for ip_addresses in links:

			if mode in [0, 2]:

				latlon_category = ip_geolocation_category.get(ip_addresses, None)
				continent_category = ip_is_oceanic_cable_continent_based.get(ip_addresses, None)
				country_category = ip_is_oceanic_cable_neighbor_based.get(ip_addresses, None)

				if latlon_category and continent_category and country_category:
				 # If by continent, we determine it oceanic, let's not process it further
					if continent_category == 'oc':
						categories_map['{}_oc'.format(latlon_category)].append(ip_addresses)
					else:
					 # Again if it's oceanic, let's mark it straight away
						if country_category == 'oc':
							categories_map['{}_oc'.format(latlon_category)].append(ip_addresses)

						else:
						 # Here we need to check if it could be a terrestrial link
							country_1 = geolocation_country_cluster.get(ip_addresses[0])
							country_2 = geolocation_country_cluster.get(ip_addresses[1])

							if country_1 and country_2:
								country_1 = country_1[0]
								country_2 = country_2[0]

							if check_country_with_landing_points(country_1, submarine_countries) and\
        check_country_with_landing_points(country_2, submarine_countries):
								categories_map['de_te'].append(ip_addresses)
							else:
								categories_map['{}_te'.format(latlon_category)].append(ip_addresses)

			if mode in [1, 2]:
				latlon_category = ip_geolocation_category_sol_validated.get(ip_addresses, None)
				continent_category = ip_is_oceanic_cable_continent_based_sol_validated.get(ip_addresses, None)
				country_category = ip_is_oceanic_cable_neighbor_based_sol_validated.get(ip_addresses, None)

				if latlon_category and continent_category and country_category:
				 # If by continent, we determine it oceanic, let's not process it further
					if continent_category == 'oc':
						categories_map_sol_validated['{}_oc'.format(latlon_category)].append(ip_addresses)
					else:
					 # Again if it's oceanic, let's mark it straight away
						if country_category == 'oc':
							categories_map_sol_validated['{}_oc'.format(latlon_category)].append(ip_addresses)

						else:
						 # Here we need to check if it could be a terrestrial link
							country_1 = geolocation_country_cluster_sol_validated.get(ip_addresses[0], None)
							country_2 = geolocation_country_cluster_sol_validated.get(ip_addresses[1], None)

							if country_1 and country_2:
								country_1 = country_1[0]
								country_2 = country_2[0]

							if check_country_with_landing_points(country_1, submarine_countries) and\
        check_country_with_landing_points(country_2, submarine_countries):
								categories_map_sol_validated['de_te'].append(ip_addresses)
							else:
								categories_map_sol_validated['{}_te'.format(latlon_category)].append(ip_addresses)

  # Let's save the results
		if mode in [0, 2]:
			save_file = 'categories_map_v{}'.format(ip_version)
			save_results_to_file(categories_map, str(save_directory), save_file)
		if mode in [1, 2]:
			save_file = 'categories_map_sol_validated_v{}'.format(ip_version)
			save_results_to_file(categories_map_sol_validated, str(save_directory), save_file)

	print (f'Only Geolocation: Counts are ->')
	print (f"Both Good - Ocean : {len(categories_map['bg_oc'])}")
	print (f"Both Good - Terrestrial : {len(categories_map['bg_te'])}")
	print (f"One Good - Ocean : {len(categories_map['og_oc'])}")
	print (f"One Good - Terrestrial : {len(categories_map['og_te'])}")
	print (f"Both Bad - Ocean : {len(categories_map['bb_oc'])}")
	print (f"Both Bad - Terrestrial : {len(categories_map['bb_te'])}")
	print (f"Terrestrial links : {len(categories_map['de_te'])}")

	print (f'SoL: Counts are ->')
	print (f"Both Good - Ocean : {len(categories_map_sol_validated['bg_oc'])}")
	print (f"Both Good - Terrestrial : {len(categories_map_sol_validated['bg_te'])}")
	print (f"One Good - Ocean : {len(categories_map_sol_validated['og_oc'])}")
	print (f"One Good - Terrestrial : {len(categories_map_sol_validated['og_te'])}")
	print (f"Both Bad - Ocean : {len(categories_map_sol_validated['bb_oc'])}")
	print (f"Both Bad - Terrestrial : {len(categories_map_sol_validated['bb_te'])}")
	print (f"Terrestrial links : {len(categories_map_sol_validated['de_te'])}")


	return categories_map, categories_map_sol_validated



def generate_country_3d_to_3c_dict():

	country_file = raw_path('iso3166-countrycodes.txt')

	with open(country_file) as fp:
		file_content = fp.readlines()

	country_3d_to_3c_dict = {'ALA' : '000'}
	res = ''
	for country in file_content[12:]:
	    a = [' '.join(item.strip().split(', ')[::-1]) for item in country.split('\t') if item.strip() != '']
	    if len(a) != 4:
	        a = [' '.join(item.strip().split(', ')[::-1]) for item in a[0].split('  ') if item.strip() != '']
	        if len(a) != 4:
	            res = a[0]
	    else:
	        a[0] = (res + ' ' + a[0]).strip()
	        country_3d_to_3c_dict[a[3]] = a[2]
	        res = ''

	return country_3d_to_3c_dict


def get_country_3c_codes (country_digit_tuple, country_3d_to_3c_dict):
	try:
	    return (country_3d_to_3c_dict[country_digit_tuple[0]], country_3d_to_3c_dict[country_digit_tuple[1]])
	except:
	    return ('xxx', 'xxx')



def get_top_country_continent_pairs (ip_version=4):

	with open(str(output_path('mapping_outputs/geolocation_country_cluster_sol_validated_v{}')).format(ip_version), 'rb') as fp:
		geolocation_country_code_cluster_map = pickle.load(fp)

	with open(str(output_path('mapping_outputs/geolocation_continent_cluster_sol_validated_v{}')).format(ip_version), 'rb') as fp:
		geolocation_continent_cluster_map = pickle.load(fp)

	with open(str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v{}')).format(ip_version), 'rb') as fp:
		final_mapping_output = pickle.load(fp)

	with open(str(result_path('mapping_outputs/categories_map_sol_validated_updated_v{}')).format(ip_version), 'rb') as fp:
		categories_map = pickle.load(fp)

	print (f'Finished loading the files')

	final_output_map = {}

	for dtype in categories_map:
		if 'te' not in dtype:
			for item in categories_map[dtype]:
				try:
					value = final_mapping_output[item]
					if isinstance(value[2], list):
						score = round(max(value[2]) * 0.5, 2)
					else:
						score = round(value[2] * 0.5, 2)
					if score != 0.0 or score != 0:
						final_output_map[item] = score 
				except:
					continue 

	mapped_links = list(final_output_map.keys())
	print (f'Length of mapped links : {len(mapped_links)}')

	country_3d_to_3c_dict = generate_country_3d_to_3c_dict()

	country_pairs_count = {}
	country_pairs_hard_count = {}
	country_pairs_links = {}

	for count, (ip_address_1, ip_address_2) in enumerate(mapped_links):
		country_1 = geolocation_country_code_cluster_map.get(ip_address_1, '')
		country_2 = geolocation_country_code_cluster_map.get(ip_address_2, '')

		if country_1 != '' and country_2 != '':
			max_index_1 = country_1[1].index(max(country_1[1]))
			country_code_1 = country_1[0][max_index_1]

			max_index_2 = country_2[1].index(max(country_2[1]))
			country_code_2 = country_2[0][max_index_2]

			current_links = country_pairs_links.get((country_code_1, country_code_2), [])
			current_links.append((ip_address_1, ip_address_2))
			country_pairs_links[(country_code_1, country_code_2)] = current_links

			current_count = country_pairs_count.get((country_code_1, country_code_2), 0)
			country_pairs_count[(country_code_1, country_code_2)] = current_count + 1
			current_count = country_pairs_hard_count.get((country_code_1, country_code_2), 0)
			try:
			    country_pairs_hard_count[(country_code_1, country_code_2)] = current_count + traceroute_dict[(ip_address_1, ip_address_2)][0]
			except:
			    pass

	sorted_country_pairs_count = {k: v for k, v in sorted(country_pairs_count.items(), key = lambda x : x[1], reverse=True)}
	sorted_country_pairs_hard_count = {k: v for k, v in sorted(country_pairs_hard_count.items(), key = lambda x : x[1], reverse=True)}

	sorted_country_pairs_hard_count_3c = {get_country_3c_codes(k, country_3d_to_3c_dict): v for k,v in sorted_country_pairs_hard_count.items()}
	sorted_country_pairs_count_3c = {get_country_3c_codes(k, country_3d_to_3c_dict): v for k, v in sorted_country_pairs_count.items()}

	country_pairs_links = {get_country_3c_codes(k, country_3d_to_3c_dict): v for k,v in country_pairs_links.items()}

	continent_pairs_count = {}
	continent_pairs_hard_count = {}

	for count, (ip_address_1, ip_address_2) in enumerate(mapped_links):
		continent_1 = geolocation_continent_cluster_map.get(ip_address_1, '')
		continent_2 = geolocation_continent_cluster_map.get(ip_address_2, '')
		if continent_1 != '' and continent_2 != '':
		    max_index_1 = continent_1[1].index(max(continent_1[1]))
		    continent_code_1 = continent_1[0][max_index_1]
      
		    max_index_2 = continent_2[1].index(max(continent_2[1]))
		    continent_code_2 = continent_2[0][max_index_2]
      
		    current_count = continent_pairs_count.get((continent_code_1, continent_code_2), 0)
		    continent_pairs_count[(continent_code_1, continent_code_2)] = current_count + 1
		    current_count = continent_pairs_hard_count.get((continent_code_1, continent_code_2), 0)
		    try:
		        continent_pairs_hard_count[(continent_code_1, continent_code_2)] = current_count + traceroute_dict[(ip_address_1, ip_address_2)][0]
		    except:
		        pass 

	sorted_continent_pairs_count = {k: v for k, v in sorted(continent_pairs_count.items(), key = lambda x : x[1], reverse=True)}
	sorted_continent_pairs_hard_count = {k: v for k, v in sorted(continent_pairs_hard_count.items(), key = lambda x : x[1], reverse=True)}

	sorted_country_pairs_count_3c_merged = {}

	for k, v in sorted_country_pairs_count_3c.items():
	    try:
	        reverse_key_value = sorted_country_pairs_count_3c[k[::-1]]
	    except:
	        reverse_key_value = 0
	    if k == k[::-1]:
	        sorted_country_pairs_count_3c_merged[k] = v 
	    else:
	        total_count = v + reverse_key_value
	        # Only add to the dict when the reverse key in not already there
	        if k[::-1] not in sorted_country_pairs_count_3c_merged.keys():
	            sorted_country_pairs_count_3c_merged[k] = total_count

	sorted_country_pairs_count_3c_merged = {k: v for k, v in sorted(sorted_country_pairs_count_3c_merged.items(), key = lambda x: x[1], reverse = True)}

	print (f'Country top 25 pairs')

	count = 0

	for key, value in sorted_country_pairs_count_3c_merged.items():
	    if len(set(key)) == 2:
	        print (f'{key}: {value}')
	        count += 1
	    if count > 25:
	        break

	print (f'Continent pairs')

	for key, value in sorted_continent_pairs_count.items():
		print (f'{key}: {value}')

	with open(str(output_path('mapping_outputs/country_pairs_links')), 'wb') as fp:
		pickle.dump(country_pairs_links, fp)


if __name__ == '__main__':

	links, all_ips = load_all_links_and_ips_data(ip_version=6)

	geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated = generate_latlon_cluster_and_score_map (all_ips, ip_version=6, mode=2, threshold=0.05)

	generate_initial_category_mapping_for_geolocation(links, geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, mode=2, geolocation_threshold=0.6, ignore=True)

	generate_categories(all_ips, links, geolocation_latlon_cluster_and_score_map, geolocation_latlon_cluster_and_score_map_sol_validated, ip_version=6, mode=2, sol_threshold=0.05, geolocation_threshold=0.6, ignore=True)
 
	# get_top_country_continent_pairs(ip_version=4)
