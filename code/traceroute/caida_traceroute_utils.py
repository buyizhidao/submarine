import os, subprocess, sys
from bs4 import BeautifulSoup
from pathlib import Path

sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

from collections import namedtuple

import subprocess, json, time, pickle

from ipaddress import ip_network, ip_address

import warnings
warnings.filterwarnings("ignore")

TraceRoute = namedtuple('TraceRoute', ['hops', 'other_info'])
Hops = namedtuple('Hops', ['hop', 'ip_address', 'rtt'])

private_ranges = [ip_network("192.168.0.0/16"), ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12")]
private_ranges_v6 = [ip_network("fc00::/7"), ip_network("fc00::/8"), ip_network("fd00::/8")]

from traceroute.caida_probe_location_info import load_probe_to_coordinate_map
from traceroute.geolocation_latency_based_validation_common_utils import load_all_geolocation_info, extract_latlon_and_perform_sol_test, fill_locations_dict_scores

# Once location scripts are done, load directly from those
Location = namedtuple('Location', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network', 'ISP', 'Org'])
MaxmindLocation = namedtuple('MaxmindLocation', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network'])

def download_warts_file (year, month, cycle_id, download_count=1000, ip_version=4):

	"""
	Download the relevant warts files in a given month, year and cycle_id
	download_count restricts the number of files downloaded. Default is 1000 to allow all downloads
	"""

	month = '{0:02d}'.format(int(month))

	if ip_version == 4:
		url = f'https://data.caida.org/datasets/topology/ark/ipv4/prefix-probing/{year}/{month}/'

		user = input('Enter CAIDA username: ')
		pwd = input('Enter the password: ')

		save_path = output_path('caida_data')
		save_file = Path(save_path / 'index.html')

		if not os.path.exists(save_path):
			os.makedirs(save_path, exist_ok = True)

		string = f'wget --user {user} --password {pwd} -O {save_file} {url}'
	else:
		url = f'https://publicdata.caida.org/datasets/topology/ark/ipv6/probe-data/{year}/{month}/'

		save_path = output_path('caida_data')
		save_file = Path(save_path / 'index_v6.html')

		if not os.path.exists(save_path):
			os.makedirs(save_path, exist_ok = True)

		string = f'wget -O {save_file} {url}'

	proc = subprocess.Popen(string, stdout=subprocess.PIPE, shell=True)
	(out, err) = proc.communicate()

	with open(save_file) as f:
		html_content = f.read()

	soup = BeautifulSoup(html_content, 'html.parser')

	count = 0

	all_links = []

	for item in soup.find_all('a'):
		link = item.get('href')
		if str(cycle_id) in link:
			all_links.append(link)

	for link in all_links:
		path = Path(save_path / link)
		path_unzipped = Path(str(path).replace('.gz', ''))
		if path.is_file() or path_unzipped.is_file():
			print (f'{link} already downloaded')
			print ()
		else:
			print (f'Downloading {link}')
			updated_url = url + link
			save_file = Path(save_path / link)
			if ip_version == 4:
				string = f'wget --user {user} --password {pwd} -O {save_file} {updated_url}'
			else:
				string = f'wget -O {save_file} {updated_url}'

			proc = subprocess.Popen(string, stdout=subprocess.PIPE, shell=True)
			(out, err) = proc.communicate()

		count += 1

		if count >= download_count:
			break


def check_if_ip_is_private (ip, v4=True):

	"""
	A simple check if a given IP is in the private IP range or not
	Returns True if in private IP range, else returns False
	"""

	if v4:
		if ip_address(ip) in private_ranges[0] or ip_address(ip) in private_ranges[1] or ip_address(ip) in private_ranges[2]:
			return True
		else:
			return False
	else:
		if ip_address(ip) in private_ranges_v6[0] or ip_address(ip) in private_ranges_v6[1] or ip_address(ip) in private_ranges_v6[2]:
			return True 
		else:
			return False


def get_caida_hops (traceroute, ip_version):
 
	"""
	Get all hops in a given traceroute that satisfy 2 conditions
	(i) Hops should be consecutive (to be considered a link)
	(ii) IP address at both ends of the link should be non-private

	Returns a list of all such hops in a traceroute which satisfy this criteria
	Also returns some counts, which are used for stats later
	"""

	if ip_version == 4:
		v4 = True 
	else:
		v4 = False 

	prev_item = traceroute.hops[0]

	actual_count = 0
	conditional_count = 0

	return_hops = []

	for index, item in enumerate(traceroute.hops[1:]):
		if isinstance(item.rtt, list):
			current_rtt_max = max(item.rtt)
			current_rtt_min = min(item.rtt)
		else:
			current_rtt_max = item.rtt
			current_rtt_min = item.rtt

		if prev_item.hop == (item.hop - 1) and not check_if_ip_is_private(prev_item.ip_address, v4) and not check_if_ip_is_private(item.ip_address, v4): 
			return_hops.append((prev_item, item))
			conditional_count += 1
		actual_count += 1

		prev_item = item

	return return_hops, actual_count, conditional_count

def process_warts_file (warts_file):

	"""
	This function does the following
	(1) Unzip the downloaded warts file
	(2) Run the scamper tool decoding to download corresponding traceroute content in json
	(3) Extract all hops in traceroutes which have either completed or in an unreachable state

	Return the decoded and processed traceroutes as a list
	"""

	if '.gz' in warts_file:
		p = subprocess.Popen(['gunzip', warts_file], stdout=subprocess.PIPE)

		out, err = p.communicate()

		print (f'Sleeping for a while to allow unzipping the file')

		time.sleep(2)

		print ('Removing the .gz file')

		try:
			os.remove(warts_file)
		except:
			pass 

	warts_file_unzip = warts_file.replace('.gz', '')

	print (f'Unzipped file is {warts_file_unzip}')

	while True:
		if Path(warts_file_unzip).is_file():
			break
		else:
			print (f'File still not unzipped, lets sleep some more time')
			time.sleep(2)

	print ()

	p = subprocess.Popen(['sc_warts2json', warts_file_unzip], stdout=subprocess.PIPE)

	out, err = p.communicate()

	dictionary_str = out.decode("UTF-8")

	list_dictionary_str = dictionary_str.split('\n')[1:]

	print (f'List dictionary size is {len(list_dictionary_str)}')

	missed_count = 0

	complete_traceroute_file_output = []

	for count, traceroute in enumerate(list_dictionary_str):

		try:
			proper_traceroute = json.loads(traceroute)

			stop_reason = proper_traceroute.get('stop_reason', '')

			if stop_reason == 'COMPLETED' or stop_reason == 'UNREACH':

				hop_0 = Hops(0, proper_traceroute['src'], 0)

				local_traceroute = TraceRoute([hop_0], {'time' : proper_traceroute['start']['ftime']})

				for hop in proper_traceroute['hops']:
					hop_content = Hops(hop['probe_ttl'], hop['addr'], hop['rtt'])
					local_traceroute.hops.append(hop_content)

				hop_last = Hops(256, proper_traceroute['dst'], hop['rtt'])

				local_traceroute.hops.append(hop_last)

			complete_traceroute_file_output.append(local_traceroute)

		except:
			missed_count += 1

	print (f'We missed {missed_count} traceroutes')

	return complete_traceroute_file_output


def geolocation_sol_validation_caida (file_traceroute, initial_lat_lon,
          iplocation_output, maxmind_output,
          ripe_output, caida_output,
          ip_location_with_penalty_and_total_count, ip_version=4):

	if ip_version == 4:
		v4 = True 
	else:
		v4 = False

	for count, traceroute in enumerate(file_traceroute):
		for contents in traceroute.hops:
			ip = contents.ip_address
			rtt = contents.rtt

			if ip and not check_if_ip_is_private(ip, v4) and rtt:

				locations = iplocation_output.get(ip, None)
				maxmind_location = maxmind_output.get(ip, None)
				ripe_location = ripe_output.get(ip, None)
				caida_location = caida_output.get(ip, None)

				prev_examined_location = ip_location_with_penalty_and_total_count.get(ip, None)

				if locations:
					for ind, location in enumerate(locations):

						status, (latitude, longitude) = extract_latlon_and_perform_sol_test(location, initial_lat_lon, rtt, ind)
						fill_locations_dict_scores(prev_examined_location, status,
						       latitude, longitude,
						       ip, ind, ip_location_with_penalty_and_total_count)

				if maxmind_location:
					status, (latitude, longitude) = extract_latlon_and_perform_sol_test(maxmind_location, initial_lat_lon, rtt, 8)
					fill_locations_dict_scores(prev_examined_location, status,
					       latitude, longitude,
					       ip, 8, ip_location_with_penalty_and_total_count)

				if ripe_location:
					status, (latitude, longitude) = extract_latlon_and_perform_sol_test(ripe_location, initial_lat_lon, rtt, 9)
					fill_locations_dict_scores(prev_examined_location, status,
					       latitude, longitude,
					       ip, 9, ip_location_with_penalty_and_total_count)

				if caida_location:
					status, (latitude, longitude) = extract_latlon_and_perform_sol_test(caida_location, initial_lat_lon, rtt, 10)
					fill_locations_dict_scores(prev_examined_location, status,
					       latitude, longitude,
					       ip, 10, ip_location_with_penalty_and_total_count)




def caida_process_traceroutes (year, month, cycle_id, ip_version=4, download_count=1000, geolocation_validation=False):

	"""
	This function puts all things together
	(1) Download the requested number of warts files from CAIDA
	(2) Process the warts file and extract relevant traceroute portions
	(3) Generate a dictionary of links with latencies
	(4) Save the dictionary from processing a warts file and then remove the earlier save dictionary (to save space)

	Returns the generated dictionary
	"""

	print (f'Stage 0: Downloading the warts files')

	download_warts_file(year, month, cycle_id, download_count, ip_version)

	print ('Finished downloading requested files')

	print ()
	print ('*' * 50)
	print ()

	if geolocation_validation:
		ip_location_with_penalty_and_total_count = {}

		print (f'First loading probe to coordinate map')

		probe_to_coordinate_map = load_probe_to_coordinate_map()

		print ('Loading all geolocation sources')

		maxmind_output, ripe_output, caida_output, iplocation_output = load_all_geolocation_info(ip_version)

		print ('Successfully loaded all geolocation results')


	save_path = save_path = output_path('caida_data')

	all_files = Path(save_path).glob('*')

	d = {}
	total_traceroutes = 0
	count = 0

	for file in all_files:
		if 'warts' in str(file) and (((ip_version == 4) and 'topo' not in str(file)) or ((ip_version == 6) and 'topo' in str(file))):
			print (f'Stage 1: Processing the file {str(file)}')
			file_traceroute = process_warts_file(str(file))
			print (f'Total file traceroutes : {len(file_traceroute)}')
			total_traceroutes += len(file_traceroute)
			print ()
			print ('*' * 50)
			print ()

			if geolocation_validation:

				print ('Stage 1.1: Performing SoL testing and validating locations')

				matched_location = [item for item in probe_to_coordinate_map.keys() if item in str(file)]

				if len(matched_location) == 1:
					initial_lat_lon = probe_to_coordinate_map[matched_location[0]]
				else:
					print (f'This should not be happening!! We got matches of {matched_location} for {str(file)}')
					print ('Proceeding anyway with the 1st output')
					initial_lat_lon = probe_to_coordinate_map[matched_location[0]]
    
				geolocation_sol_validation_caida(file_traceroute, initial_lat_lon,
				        iplocation_output, maxmind_output,
				        ripe_output, caida_output,
				        ip_location_with_penalty_and_total_count, ip_version)

				print (f'Our current ip_location_with_penalty_and_total_count length is {len(ip_location_with_penalty_and_total_count)}')

				print (f'Lets save the current result')

				with open(str(output_path('location_data/caida_validated_ip_locations_v{}')).format(ip_version), 'wb') as fp:
					pickle.dump(ip_location_with_penalty_and_total_count, fp, protocol=pickle.HIGHEST_PROTOCOL)

				print (f'Finished saving the results')


			print ('Stage 2: Extracting big hops')
			for index, traceroute in enumerate(file_traceroute):
				caida_hops, actual_caida_hops, conditional_caida_hops = get_caida_hops(traceroute, ip_version)
    
				for a_caida_hop in caida_hops:
				    ip_addresses = (a_caida_hop[0].ip_address, a_caida_hop[1].ip_address)
				    all_latencies = d.get(ip_addresses, [])

				    if isinstance(a_caida_hop[0].rtt, list):
				        hop_0_min = min(a_caida_hop[0].rtt)
				    else:
				        hop_0_min = a_caida_hop[0].rtt

				    if isinstance(a_caida_hop[1].rtt, list):
				        hop_1_min = min(a_caida_hop[1].rtt)
				    else:
				        hop_1_min = a_caida_hop[1].rtt

				    latency_min = round((hop_1_min - hop_0_min) / 2, 2)
				    all_latencies.append(latency_min)
				    d[ip_addresses] = all_latencies

			file_name = f'uniq_ip_dict_caida_all_links_v{ip_version}_min_all_latencies_only_' + str(count)

			save_file = save_path / file_name

			print (f'The save file is {str(save_file)} and current dictionary length is {len(d)}')

			with open(save_file, 'wb') as fp:
				pickle.dump(d, fp, protocol=pickle.HIGHEST_PROTOCOL)

			print ()
			print ('*' * 50)
			print ()

			remove_file_name = f'uniq_ip_dict_caida_all_links_v{ip_version}_min_all_latencies_only_' + str(count - 1)

			remove_file = save_path / remove_file_name

			try:
				print (f'Trying to remove the file {str(remove_file)}')
				os.remove(remove_file)
			except:
				pass

			print ()
			print ('*' * 50)
			print ()

			count += 1

	return d

if __name__ == '__main__':

	result = caida_process_traceroutes(2022, 3, 1647, 6, 1000, True)

	print (f'Final dictionary length : {len(result)}')
