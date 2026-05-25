import pickle, subprocess, json, re, pycountry
from collections import namedtuple

import string, time
from nltk.corpus import stopwords
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import CountVectorizer

from pathlib import Path
import numpy as np

import os, sys, time
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

from itertools import permutations, combinations, product
from ripe.atlas.cousteau import (Traceroute, AtlasSource, AtlasCreateRequest)

from utils.as_utils import get_ip_to_asn_for_all_ips

from haversine import haversine

from validation.identifying_links_to_single_org import generate_as_to_org_map_from_caida

Cable = namedtuple('Cable', ['name', 'landing_points', 'length', 'owners', 'notes', 'rfs', 'other_info'])

LandingPoints = namedtuple('LandingPoints', ['latitude', 'longitude', 'country', 'location', 'cable'])

from ipaddress import ip_network, ip_address
private_ranges = [ip_network("192.168.0.0/16"), ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12")]

prepend_path = './'

stopwords_raw = stopwords.words('english')
special_stopwards = ['telecom', 'company', 'cable', 'telecommunications', 'international', 'corporation', 'ltd', 'group', 'telecommunication', 'communications', 'limited', 'inc', 'infrastructure', 'technologies', 'llc', 'plc']
stopwords = stopwords_raw + special_stopwards
import Levenshtein

def load_landing_points_info():

	with open(prepend_path + str(raw_path('submarine_data/landing_points_dict')), 'rb') as fp:
		landing_points = pickle.load(fp)

	return landing_points



def load_cables_info():

	with open(prepend_path + str(raw_path('submarine_data/cable_info_dict')), 'rb') as fp:
		cable_info = pickle.load(fp)

	return cable_info



def get_asn_to_submarine_owners_mapping():

	save_file = output_path('mapping_outputs/submarine_owner_to_asn_list')

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			submarine_owners_to_asn_map = pickle.load(fp)

		asn_to_submarine_owners_map = {}
		for owner, asn_list in submarine_owners_to_asn_map.items():
			for asn in asn_list:
				current_owners = asn_to_submarine_owners_map.get(asn, [])
				current_owners.append(owner)
				asn_to_submarine_owners_map[asn] = current_owners

	else:
		print (f'submarine owner to asn list not generated!! Generate it by running the as_utils script')
		sys.exit(1)

	return submarine_owners_to_asn_map, asn_to_submarine_owners_map



def check_if_probe_asn_in_owner_asns (probe_asn, owners_list, submarine_owners_to_asn_map):

	for owner in owners_list:
		try:
			if probe_asn in submarine_owners_to_asn_map[owner]:
				return True, owner
		except:
			continue 

	return False, None



def save_selected_probes_for_cable (cable_probe_search, tags='default'):

	with open('validation/selected_probes_per_cable_{}'.format(tags), 'wb') as fp:
		pickle.dump(cable_probe_search, fp)



def select_probes_for_cables (landing_points, cable_info, submarine_owners_to_asn_map, tags='default'):

	cable_probe_search = {}

	query_string = "ripe-atlas probe-search --center='{},{}' --radius {} --status 1  --field id --field address_v4 --field country --field asn_v4 --limit 100"

	# We will start with a radius of 50 km and then expand our search radius
	initial_radius = 50

	for count, (landing_point_id, point) in enumerate(landing_points.items()):
		attempt = 0 
		# print (f'We are checking for {point.location} and cables at this point are {point.cable}')

		while attempt < 3:
			cmd_str = query_string.format(point.latitude, point.longitude, initial_radius * (2 ** attempt))
			p = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE)
			output = p.communicate()[0].decode()

			# print (f'At attempt {attempt}, we get : ')

			available_probes = output.split('====================================')[1]

			if available_probes != '\n':

			 # Checking and eliminating probes with empty info and/or have no IP address (which renders the probe useless for our purpose)
				probe_details = [item.split() for item in available_probes.split('\n') if item != '' and item.split()[1] != 'None']

				probe_asns = [item[-1] for item in probe_details]

				for index, asn in enumerate(probe_asns):
					for cable in point.cable:
						cable_details = cable_info[cable]
						cable_name = cable_details.name
						if cable_details.rfs <= 2021:
							is_match, owner = check_if_probe_asn_in_owner_asns(asn, cable_details.owners, submarine_owners_to_asn_map)
							if is_match:
								current_probes = cable_probe_search.get(cable_name, [])
								# First let's check if this probe was there in an earlier attempt
								if len([item for item in current_probes if item[1][0] == probe_details[index][0]]) == 0:
									current_probes.append((point.location, probe_details[index], attempt, owner))
								cable_probe_search[cable_name] = current_probes


			attempt += 1

		if count % 10 == 0:
			print (f'Processed {count} of {len(landing_points)}')
			save_selected_probes_for_cable(cable_probe_search, tags)

	save_selected_probes_for_cable(cable_probe_search, tags)

	return cable_probe_search


def check_probe_validity(probe_id):

	query_string = "ripe-atlas probe-info {}".format(probe_id)

	p = subprocess.Popen(query_string, shell=True, stdout=subprocess.PIPE)
	output = p.communicate()[0].decode()

	search = re.search(r'Status(\s*)(\w*)\n', output)
	status = search.group(2)

	if status != 'Connected':
		return False
	else:
		return True



def create_ripe_atlas_request(probe_pairs, measurements, cable, owner, ripe_api_key, custom_term):

 # probe_id and IP in that order
	probe_1 = (probe_pairs[0][0][1][0][0], probe_pairs[0][0][1][0][1])
	probe_2 = (probe_pairs[1][0][1][0][0], probe_pairs[1][0][1][0][1])

	probe_1_near_landing_point_location = probe_pairs[0][0][0]
	probe_2_near_landing_point_location = probe_pairs[1][0][0]

	probes = (probe_1, probe_2)

	probe_locations = (probe_1_near_landing_point_location, probe_2_near_landing_point_location)

	# Checking probe validity
	probe_1_valid = check_probe_validity(probe_1[0])
	probe_2_valid = check_probe_validity(probe_2[0])

	if probe_1_valid and probe_2_valid:
		for index in range(len(probes)):
			source = AtlasSource(type='probes', value=probes[index%2][0], requested=1)
			traceroute = Traceroute(af=4, target=probes[(index+1)%2][1], description=f'{custom_term} validation', protocol='ICMP')

			request = AtlasCreateRequest(key=ripe_api_key, measurements=[traceroute], sources=[source], is_oneoff=True)

			print (f'source: {probes[index%2]} at location {probe_locations[index%2]}')
			print (f'target: {probes[(index+1)%2]} at location {probe_locations[(index+1)%2]}')

			(is_success, response) = request.create()

			if is_success:
				print (f"Request ID: {response['measurements'][0]}")
				current_measurements = measurements.get(cable, [])
				current_measurements.append(((probe_locations[index%2], probe_locations[(index+1)%2]), (probes[index%2], probes[(index+1)%2]), owner, response['measurements'][0]))
				measurements[cable] = current_measurements
			else:
				print (f'Creating request failed for {source.value} as source and {traceroute.target} as target')


	print ('*' * 50)


def generate_cable_measurements (cable_probe_search, ripe_api_key, custom_term):

	cable_measurements = {}
	total_count = 0
	perfect_match_count = 0
	error_countries = {'russia': 'ru', 'brunei': 'bn', 'micronesia': 'fm', 'iran': 'ir'}

	measurements = {}

	for count, (cable, probe_near_landing_points) in enumerate(cable_probe_search.items()):
	 # uniq_landing_points = set([item[0] for item in probe_near_landing_points if pycountry.countries.lookup(item[0].split(',')[-1].strip()).lower() == item[1][2]])
		uniq_landing_points = set()
		uniq_landing_points_to_probes = {}
		valid_uniq_landing_points = {}
		for item in probe_near_landing_points:
			country = item[0].split(',')[-1].strip()
			try:
				alpha_2 = pycountry.countries.lookup(country).alpha_2.lower()
				if alpha_2 == item[1][2]:
					uniq_landing_points.add(item[0])
					current_probes = uniq_landing_points_to_probes.get(item[0], [])
					if item[-1] not in [i[-1] for i in current_probes] and item[1][1] != 'None':
						current_probes.append((item[1], item[2], item[3]))
					uniq_landing_points_to_probes[item[0]] = current_probes
   
			except:
				alpha_2 = error_countries.get(country.lower(), None)
				if alpha_2 == item[1][2]:
					uniq_landing_points.add(item[0])
					current_probes = uniq_landing_points_to_probes.get(item[0], [])
					if item[-1] not in [i[-1] for i in current_probes] and item[1][1] != 'None':
						current_probes.append((item[1], item[2], item[3]))
					uniq_landing_points_to_probes[item[0]] = current_probes
   
				else:
				 # print (f'Error: {country} and {item}')
					pass
				continue


		if len(uniq_landing_points) > 1:
			valid_uniq_landing_points = {i: uniq_landing_points_to_probes[i] for i in list(uniq_landing_points) if len(uniq_landing_points_to_probes[i]) > 0}
			if len(valid_uniq_landing_points) > 1:
				total_count += 1
				all_landing_point_permutations = combinations(valid_uniq_landing_points.keys(), 2)
				for permutation in all_landing_point_permutations:
					common_owners = set([item[-1] for item in valid_uniq_landing_points[permutation[0]]]) & set([item[-1] for item in valid_uniq_landing_points[permutation[1]]])
					if len(common_owners) > 0:
						for owner in list(common_owners):
							matched_probe_1 = [(permutation[0], item) for item in valid_uniq_landing_points[permutation[0]] if item[-1] == owner]
							matched_probe_2 = [(permutation[1], item) for item in valid_uniq_landing_points[permutation[1]] if item[-1] == owner]
       
							# Checking if countries are not same
							if matched_probe_1[0][1][0][2] != matched_probe_2[0][1][0][2]:
								print (f'cable: {cable}, owner: {owner}')
								create_ripe_atlas_request((matched_probe_1, matched_probe_2), measurements, cable, owner, ripe_api_key, custom_term)
								print ('*' * 50)
								perfect_match_count += 1


	print (json.dumps(measurements, indent=4))


	print (total_count)
	print (perfect_match_count)

	with open('validation/measurements_done_strict_constraints', 'wb') as fp:
		pickle.dump(measurements, fp)



def generate_asns_pairs_across_landing_points (landing_points):

	with open(str(output_path('mapping_outputs/all_ips_v4')), 'rb') as fp:
		all_ips = pickle.load(fp)

	ip_to_asn_dict = get_ip_to_asn_for_all_ips(all_ips)

	print ('Loading the cable mapping')

	with open(str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v4')), 'rb') as fp:
		cable_mapping = pickle.load(fp)





def check_if_ip_is_private (ip, v4=True):

	"""
	A simple check if a given IP is in the private IP range or not
	Returns True if in private IP range, else returns False
	"""

	if ip_address(ip) in private_ranges[0] or ip_address(ip) in private_ranges[1] or ip_address(ip) in private_ranges[2]:
		return True
	else:
		return False


def extract_traceroute_info (measurement_ids_list):

	high_latency_hops = {}

	for count, (cable, landing_points, owners, measurement) in enumerate(measurement_ids_list):

		print (f'Currently processing {measurement}')
		traceroute_hops = {}
		all_latency_links = {}

		cmd_str = 'ripe-atlas report {}'.format(measurement)
		p = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
		traceroute_result = p.communicate()[0].decode().split('\n')[4:-1]

		print ('\n'.join(traceroute_result))

		prev_rtt = 0
		max_rtt = 0

		for line in traceroute_result:
			line_split = line.replace('ms', '').split()
			try:
				hop_num = int(line_split[0])
				ip = line_split[1]
				rtts = [float(item) for item in line_split[2:] if item.replace('.', '').isdigit()]

				if ip != '*' and len(rtts) > 0:
					current_hop_contents = traceroute_hops.get(hop_num, {})
					current_hop_contents[ip] = sum(rtts)/len(rtts)
					traceroute_hops[hop_num] = current_hop_contents
					current_rtt = sum(rtts)/len(rtts)
					if current_rtt - prev_rtt > max_rtt:
						max_rtt = current_rtt - prev_rtt
					prev_rtt = current_rtt

			except Exception as e:
				print (f'Got error {str(e)}')
				continue

		if len(traceroute_hops) > 1:
			for hop_num, contents in traceroute_hops.items():
    
			 # Checking if we have values for 
				if (hop_num+1) in traceroute_hops.keys():
					all_combinations = product(contents.keys(), traceroute_hops[hop_num+1].keys())
					for combination in all_combinations:
						latency_diff = traceroute_hops[hop_num+1][combination[1]] - contents[combination[0]]
						all_latency_links[combination] = latency_diff

			if len(all_latency_links) > 0:
			 # Finding the link with the highest latency
				max_link, consecutive_max_rtt = max(all_latency_links.items(), key=lambda x:x[1])
				if round(consecutive_max_rtt, 3) >= round(max_rtt, 3) and not check_if_ip_is_private(max_link[0]) and not check_if_ip_is_private(max_link[1]):
					high_latency_hops[max_link] = {'cable': cable, 'landing_points': landing_points, 'owners': owners, 'measurement': measurement}
				else:
					print (f'max latency overall was {max_rtt}, but consecutive one we got was {consecutive_max_rtt}')

		print ('#' * 50)

	return high_latency_hops


def select_probes_for_links_list (all_links, geo_latlon_cluster, ip_to_asn_dict, ip_to_closest_submarine_org, asn_to_probe_id_map, probe_to_coordinate_map):

	all_matches = {}
	radius = 50
	matches = 0

	for count, link in enumerate(all_links):
		common_owners = set(link) & set(ip_to_closest_submarine_org.keys())
  
		if len(common_owners) > 0:
			end_probe_matches = []
			for ip in link:
				value = geo_latlon_cluster[ip]
				max_value = max(value[1])
				max_location_index = value[1].index(max_value)
				selected_location = np.mean(value[0][max_location_index], axis=0).tolist()

				ip_asn = ip_to_asn_dict.get(ip, None)
				if ip_asn:
				 # Let's check if we have a probe in this asn
					probes = asn_to_probe_id_map.get(ip_asn, None)
					if probes:
					 # Now let's check if there is a probe within 50 km radius
						selected_probes = [(probe, probe_to_coordinate_map[probe][0]) for probe in probes if haversine(selected_location, probe_to_coordinate_map[probe][1]) <= radius]
						if len(selected_probes) > 0:
							end_probe_matches.append(selected_probes[0])

			if len(end_probe_matches) == 2:
				all_matches[link] = end_probe_matches
				matches += 1

		if count % 1000 == 0:
			print (f'Processed {count} of {len(all_links)} and currently we have {matches} matches')
			if count % 10000 == 0:
				print ('Doing a partial save')
				with open('validation/select_probes_loose_constraints', 'wb') as fp:
					pickle.dump(all_matches, fp)

	print (f'We got probes for {matches} links')
	return all_matches



def run_ripe_query_for_all_probe_locations():

	if Path('validation/asn_to_probe_id_map').exists() and Path('validation/probe_to_coordinate_map').exists():
		print ('Loading the saved files directly')

		with open('validation/asn_to_probe_id_map', 'rb') as fp:
			asn_to_probe_id_map = pickle.load(fp)

		with open('validation/probe_to_coordinate_map', 'rb') as fp:
			probe_to_coordinate_map = pickle.load(fp)

	else:

		p = subprocess.Popen('ripe-atlas probe-search --all --status 1 --field id --field address_v4 --field coordinates --field asn_v4 --field status', 
		                    shell=True, stdout=subprocess.PIPE)
		result = p.communicate()[0].decode()

		entry_list = result.split('\n')[3:-5]
		probe_entries = [tuple(item.split()) for item in entry_list]

		probe_to_coordinate_map = {}
		asn_to_probe_id_map = {}

		for item in probe_entries:
			lat_lon_tuple = tuple(map(float, item[2].split(',')))
			if item[-1] == 'Connected' and item[1] != 'None' and item[1] != None:
			 # -1111.0 is used to tag all probes for which location is unknown (these are typically not public probes)
				if -1111.0 not in lat_lon_tuple:
					probe_to_coordinate_map[item[0]] = (item[1], lat_lon_tuple)
					current_ids = asn_to_probe_id_map.get(item[3], [])
					current_ids.append(item[0])
					asn_to_probe_id_map[item[3]] = current_ids

		with open('validation/asn_to_probe_id_map', 'wb') as fp:
			pickle.dump(asn_to_probe_id_map, fp)

		with open('validation/probe_to_coordinate_map', 'wb') as fp:
			pickle.dump(probe_to_coordinate_map, fp)

	return asn_to_probe_id_map, probe_to_coordinate_map


def load_latlon_closest_submarine_and_category_info():

	save_directory = output_path('mapping_outputs')

	categories_map_file = 'categories_map_sol_validated_v4'

	if Path(save_directory/categories_map_file).exists():
		with open(save_directory/categories_map_file, 'rb') as fp:
			categories_map = pickle.load(fp)

	else:
		print ('Missing the categories map file, exiting now!')
		sys.exit(1)

	latlon_cluster_file = 'geolocation_latlon_cluster_and_score_map_sol_validated_v4'

	if Path(save_directory/latlon_cluster_file).exists():
		with open(save_directory/latlon_cluster_file, 'rb') as fp:
			geo_latlon_cluster = pickle.load(fp)

	else:
		print ('Missing the latlon cluster file')
		sys.exit(1)

	ip_to_closest_submarine_file = 'ip_to_closest_submarine_org_v4'

	if Path(save_directory/ip_to_closest_submarine_file).exists():
		with open(save_directory/ip_to_closest_submarine_file, 'rb') as fp:
			ip_to_closest_submarine_org = pickle.load(fp)

	else:
		print ("Missing the ip to closest submanrine org file")
		sys.exit(1)

 # Let's consider only bg_oc and og_oc categories
	all_links = categories_map['bg_oc']
	all_links.extend(categories_map['og_oc'])

	all_ips = set()

	for link in all_links:
		all_ips.add(link[0])
		all_ips.add(link[1])

	all_ips = list(all_ips)

	return geo_latlon_cluster, all_links, all_ips, ip_to_closest_submarine_org



def ripe_request_for_single_probe_pair (probes, ripe_api_key, custom_term):

	probe_1_valid = check_probe_validity(probes[0][0])
	probe_2_valid = check_probe_validity(probes[1][0])

	if probe_1_valid and probe_2_valid:
	 # By default our first item is the source probe and the second one the target
		source = AtlasSource(type='probes', value=probes[0][0], requested=1)
		traceroute = Traceroute(af=4, target=probes[1][1], description=f'{custom_term}-validation', protocol='ICMP')
		request = AtlasCreateRequest(key=ripe_api_key, measurements=[traceroute], sources=[source], is_oneoff=True)

		(is_success, response) = request.create()

		if is_success:
			return True, str(response['measurements'][0])
		else:
			return False, None
	else:
		return False, None


def initiate_ripe_probe_measurements(uniq_probes, ripe_api_key, custom_term, limit=1000):

	successful_measurements = 0
	save_file = 'validation/current_running_measurements_loose_constraints'

	probes_to_measurements_map = {}

	if Path(save_file).exists():
  
		with open(save_file, 'rb') as fp:
			probes_to_measurements_map = pickle.load(fp)

		if len(probes_to_measurements_map) >= limit:
			print('Looks like we already had finished earlier, returning right away')
			return probes_to_measurements_map
  
		measurements_in_queue = [item for item in probes_to_measurements_map.values() if item != None]
		successful_measurements += len(measurements_in_queue)
		print (f'Loaded {len(measurements_in_queue)} from previous run. It may be higher than 100, but we will eliminate most of them through our check later on')
 
	else:
		print (f'No prior runs, lets start with a clean slate')
		measurements_in_queue = []

	for count, probes in enumerate(uniq_probes):

		if probes:

		 # RIPE has a rate limit, so we will monitor measurements for completion and checking if we have processed earlier
			if len(measurements_in_queue) <= 100:
				if probes in probes_to_measurements_map.keys():
					print (f'We have processed {probes} earlier, so skipping it over')
					continue
				else:
					is_success, measurement_id = ripe_request_for_single_probe_pair(probes, ripe_api_key, custom_term)
					if is_success:
						measurements_in_queue.append(measurement_id)
						successful_measurements += 1
					probes_to_measurements_map[probes] = measurement_id

				if successful_measurements >= limit:
					break

			else:
				print ('We hit the ceiling of 100 measurements, lets try to poll for completion of some measurements')
    
				while True:
					query_string = f'ripe-atlas measurement-search --search "{custom_term}" --field id --field status --limit 1000 --status ongoing'
					p = subprocess.Popen(query_string, shell=True, stdout=subprocess.PIPE)
					query_result = p.communicate()[0].decode()
					available_measurements = query_result.split('==========================')[1]
					measurement_to_status_map = {item.split()[0]: item.split()[1] for item in available_measurements.split('\n') if item != ''}

					# Only the measurements which have the status of ongoing are extracted, so we will only take those and remove the rest
					measurements_in_queue = list(set(measurements_in_queue) & set(measurement_to_status_map.keys()))

					if len(measurements_in_queue) >= 100:
						print ('We will sleep for 60 seconds and re-try')
						time.sleep(60)
					else:
						print (f'We have successfully finished {100-len(measurements_in_queue)} measurements')
						break

  # Let's save the results for every 10 entries
		if count % 10 == 0:
			print (f'Doing a partial save, processed {count} of {len(uniq_probes)}. Measurments initiated: {len(probes_to_measurements_map)}')
			with open(save_file, 'wb') as fp:
				pickle.dump(probes_to_measurements_map, fp)

 # Let's save the final results
	with open(save_file, 'wb') as fp:
		pickle.dump(probes_to_measurements_map, fp)

	return probes_to_measurements_map
  

if __name__ == '__main__':

	landing_points = load_landing_points_info()
	cable_info = load_cables_info()
	submarine_owners_to_asn_map, asn_to_submarine_owners_map = get_asn_to_submarine_owners_mapping()

	ripe_api_key = input('Enter RIPE key: ')
	custom_term = input('Enter custom term for RIPE measurement creation : ')

	tags = 'final'

	operation_mode = sys.argv[1]

	# strict constraints (probe search and initiate traceroute)
	if operation_mode == 's':
	 # Check if file already exists
		path = Path(Path.cwd() / 'validation/selected_probes_per_cable_{}'.format(tags))

		if path.is_file():
			print ('Loading directly from file')
			with open(path, 'rb') as fp:
				cable_probe_search = pickle.load(fp)
		else:
			print ('Performing queries to identify probes')
			cable_probe_search = select_probes_for_cables(landing_points, cable_info, submarine_owners_to_asn_map, tags)

		print (len(cable_probe_search))

		generate_cable_measurements (cable_probe_search, ripe_api_key, custom_term)

	if operation_mode == 'l':

		path = Path(Path.cwd() / 'validation/select_probes_loose_constraints')

		if path.is_file():
			print (f'Loading the file directly')
			with open(path, 'rb') as fp:
				all_results = pickle.load(fp)

		else:
			geo_latlon_cluster, all_links, all_ips, ip_to_closest_submarine_org = load_latlon_closest_submarine_and_category_info()
			ip_to_asn_dict = get_ip_to_asn_for_all_ips(all_ips)
     
			asn_to_probe_id_map, probe_to_coordinate_map = run_ripe_query_for_all_probe_locations()
			all_results = select_probes_for_links_list (all_links, geo_latlon_cluster, ip_to_asn_dict, ip_to_closest_submarine_org, asn_to_probe_id_map, probe_to_coordinate_map)

			with open('validation/select_probes_loose_constraints', 'wb') as fp:
				pickle.dump(all_results, fp)

		uniq_probes = list(set([tuple(item) for item in all_results.values()]))

		print (f'We have {len(uniq_probes)} combinations of unique probe pairs which satisfied our constraints')

		probes_to_measurements_map = initiate_ripe_probe_measurements(uniq_probes, ripe_api_key, custom_term, limit=5000)


  
 # Extract the important hops from a measurement
	if operation_mode == 'e':

		constraint_mode = sys.argv[2]

		if constraint_mode == 's':
			with open('validation/measurements_done_strict_constraints', 'rb') as fp:
				measurement_details = pickle.load(fp)

			measurement_ids_list = [(cable, i[0], i[2], i[-1]) for cable, content in measurement_details.items() for i in content]

			high_latency_hops = extract_traceroute_info(measurement_ids_list)

			print_high_latency_hops = {str(k): v for k,v in high_latency_hops.items()}

			print (json.dumps(print_high_latency_hops, indent=4))

			print (high_latency_hops.keys())

		if constraint_mode == 'l':
			with open('validation/current_running_measurements_loose_constraints', 'rb') as fp:
				probes_to_measurements_map = pickle.load(fp)

			measurement_ids_list = [(None, None, None, item) for item in probes_to_measurements_map.values()]

			high_latency_hops = extract_traceroute_info(measurement_ids_list)

			print_high_latency_hops = {str(k): v for k,v in high_latency_hops.items()}

			print (json.dumps(print_high_latency_hops, indent=4))

			print (high_latency_hops.keys())

			with open('validation/high_latency_links_loose_constraints', 'wb') as fp:
				pickle.dump(high_latency_hops, fp)

