import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import get_logger

import calendar
from datetime import datetime, timezone, timedelta

import requests
import pickle
import json

from collections import namedtuple

from pathlib import Path

from ipaddress import ip_network, ip_address

TraceRoute = namedtuple('TraceRoute', ['hops', 'other_info'])

Hops = namedtuple('Hops', ['hop', 'ip_address', 'rtt'])

private_ranges = [ip_network("192.168.0.0/16"), ip_network("10.0.0.0/8"), ip_network("172.16.0.0/12")]

private_ranges_v6 = [ip_network("fc00::/7"), ip_network("fc00::/8"), ip_network("fd00::/8")]

from traceroute.ripe_probe_location_info import load_probe_location_result
from traceroute.geolocation_latency_based_validation_common_utils import load_all_geolocation_info, extract_latlon_and_perform_sol_test, fill_locations_dict_scores

# Once location scripts are done, load directly from those
Location = namedtuple('Location', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network', 'ISP', 'Org'])
MaxmindLocation = namedtuple('MaxmindLocation', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network'])

logger = get_logger(__name__)


def _time_slug(value):
	return value.strftime("%m_%d_%Y_%H_%M")


def _resume_state_file(save_directory, msm_id, ip_version, start_time, end_time):
	return save_directory / 'ripe_resume_state_{}_v{}_{}_to_{}'.format(
	 msm_id,
	 ip_version,
	 _time_slug(start_time),
	 _time_slug(end_time),
	)


def _resume_checkpoint_file(save_directory, msm_id, ip_version, start_time, end_time):
	return save_directory / 'ripe_resume_checkpoint_{}_v{}_{}_to_{}'.format(
	 msm_id,
	 ip_version,
	 _time_slug(start_time),
	 _time_slug(end_time),
	)

def _parse_ripe_atlas_response(response):
	"""
	RIPE Atlas can stream large result sets. Prefer format=txt, where each line is
	one JSON object, but keep support for the JSON array format for cached/older
	responses.
	"""
	response.raise_for_status()

	parsed_results = []
	array_payload = []

	for line in response.iter_lines(decode_unicode=True):
		if not line:
			continue
		line = line.strip()
		if not line:
			continue

  # JSON array fallback. This is not the preferred path for large windows,
  # but it keeps the function compatible with the default RIPE API format.
		if line.startswith('[') or array_payload:
			array_payload.append(line)
			continue

		try:
			parsed_results.append(json.loads(line))
		except json.JSONDecodeError as exc:
			raise ValueError(
			 'Failed to parse RIPE Atlas result line as JSON. '
			 'The API response may be truncated or not in txt format. '
			 f'First 200 chars: {line[:200]}'
			) from exc

	if array_payload:
		payload = ''.join(array_payload)
		try:
			return json.loads(payload)
		except json.JSONDecodeError as exc:
			raise ValueError(
			 'Failed to parse RIPE Atlas JSON array response. '
			 'Retry with smaller --chunk-hours or use format=txt. '
			 f'Payload length: {len(payload)}'
			) from exc

	return parsed_results


def download_data_from_ripe_atlas (start_time, end_time, msm_id, return_content = 0):

	"""
	This function essentially downloads the data from RIPE Atlas website and saves the 
	result in the data/intermediate directory
	Inputs
		start_time -> The start time to collect the data (should be in datetime format)
		end_time -> The end time for the traceroutes to be collected (should be in datetime format)
		return_content -> By default 0, if set to 1, we return the last processed traceroutes
	"""

	fixed_url = "atlas.ripe.net/api/v2/measurements/"

	start_time_int = int(calendar.timegm(start_time.timetuple()))
	end_time_int = int(calendar.timegm(end_time.timetuple()))

	save_directory = output_path('ripe_data')

	if not os.path.exists(save_directory):
		os.makedirs(save_directory, exist_ok = True)

	current_process_time = datetime.fromtimestamp(start_time_int, tz = timezone.utc).strftime("%m_%d_%Y_%H_%M")
	current_process_end_time = datetime.fromtimestamp(end_time_int, tz = timezone.utc).strftime("%m_%d_%Y_%H_%M")

	file_name = 'raw_output_' + msm_id + '_' + current_process_time + '_to_' + current_process_end_time

	if Path(save_directory / file_name).exists():
  
		save_file = save_directory / file_name
  
		with open(save_file, 'rb') as fp:
			print ('Directly loading contents from stored file')
			response_list = pickle.load(fp)
 
	else:
  
		print (f"Currently processing traceroutes starting from {current_process_time}.")

		url = "https://{0}{1}/results/".format(fixed_url, msm_id)
		params = {
		 'start': start_time_int,
		 'stop': end_time_int,
		 'format': 'txt',
		}
  
		response = requests.get(url, params=params, stream=True, timeout=(15, 180))
		response_list = _parse_ripe_atlas_response(response)

		save_file = save_directory / file_name

		with open(save_file, 'wb') as fp:
			pickle.dump(response_list, fp, protocol=pickle.HIGHEST_PROTOCOL)

		print ("Finished processing all the traceroutes in the given data range.")

	if return_content:
		return (response_list, save_file)



def process_transform_traceroute (traceroute_data, save_file, return_content = 0):

	"""
	This function essentially extracts required portions of the traceroute, removes hops with
	non-useful entries and saves the output to the data/intermediate directory
	Input
		traceroute_data -> List of all traceroutes (Essentially pass the output from download_data_from_ripe_atlas or read raw_output_*** file)
		save_file -> The file to which the processed output should be written
	"""

	output_traceroute = []
	skipped_traceoute = []
	count = 1

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			print ('Directly loading file from saved locations')
			output_traceroute = pickle.load(fp)

	else:
		for traceroute in traceroute_data:
			try:
				hops = {0: [Hops(0, traceroute['src_addr'], 0)]}
				for hop in traceroute['result']:
					ips_to_rtts = []
					hop_num = hop['hop']
					for i in hop['result']:
						rtt = i.get('rtt', None)
						ip = i.get('from', None)
						if ip and rtt:
							ips_to_rtts.append(Hops(hop_num, ip, rtt))
					if len(ips_to_rtts) > 0:
						hops[hop_num] = ips_to_rtts
						last_rtt = rtt
				hops[256] = [Hops(256, traceroute['dst_addr'], last_rtt)]
				output_traceroute.append(TraceRoute(hops, {'time' : datetime.fromtimestamp(traceroute['timestamp']), 'probe_id': traceroute['prb_id']}))
			except:
				skipped_traceoute.append(traceroute)
   
			count += 1

		print (f"Skipped traceroutes : {len(skipped_traceoute)}")

		print (f"Total count now is {count}")

		with open(save_file, 'wb') as fp:
			pickle.dump(output_traceroute, fp, protocol=pickle.HIGHEST_PROTOCOL)


	if return_content:
		return output_traceroute



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



def geolocation_sol_validation_ripe (updated_traceroute_output, probe_to_coordinate_map,
         iplocation_output, maxmind_output,
         ripe_output, caida_output,
         ip_location_with_penalty_and_total_count, v4=True):

	for count, traceroute in enumerate(updated_traceroute_output):
		probe = traceroute.other_info['probe_id']
		initial_lat_lon = probe_to_coordinate_map[str(probe)][1]

		for key, contents in traceroute.hops.items():

		 # As the same IP could be repeated based on the # of probes sent, let's not look at the huge geolocation sources 
		 # again and again. Kind of like a local cache
			local_dict = {}

			for hop_info in contents:
				ip = hop_info.ip_address
				rtt = hop_info.rtt

				if ip and not check_if_ip_is_private(ip, v4):

					if ip not in local_dict.keys():
      
						locations = iplocation_output.get(ip, None)
						maxmind_location = maxmind_output.get(ip, None)
						ripe_location = ripe_output.get(ip, None)
						caida_location = caida_output.get(ip, None)

						# Updating the local cache
						local_dict[ip] = {'locations': locations, 'maxmind_location': maxmind_location,
						     'ripe_location': ripe_location, 'caida_location': caida_location}

					else:

						locations = local_dict[ip]['locations']
						maxmind_location = local_dict[ip]['maxmind_location']
						ripe_location = local_dict[ip]['ripe_location']
						caida_location = local_dict[ip]['caida_location']

     
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




def get_ripe_hops (traceroute, v4=True):
 
	"""
	Get all hops in a given traceroute that satisfy 2 conditions
	(i) Hops should be consecutive (to be considered a link)
	(ii) IP address at both ends of the link should be non-private

	Returns a list of all such hops in a traceroute which satisfy this criteria
	Also returns some counts, which are used for stats later
	"""

	prev_item = traceroute.hops[0]
	prev_ip_to_rtt = {prev_item[0].ip_address: [prev_item[0].rtt]}

	actual_count = 0
	conditional_count = 0

	return_hops = []

	for index, (key,item) in enumerate(traceroute.hops.items()):
		if key != 0:
			ip_to_rtt = {}
			hop_num = item[0].hop
			for hop_info in item:
				current_rtt_info = ip_to_rtt.get(hop_info.ip_address, [])
				if hop_info.rtt:
					current_rtt_info.append(hop_info.rtt)
					ip_to_rtt[hop_info.ip_address] = current_rtt_info

			for ip, rtt in ip_to_rtt.items():
				current_rtt_max = max(rtt)
				current_rtt_min = min(rtt)

				for prev in prev_item:
					if prev.hop == (hop_num - 1) and not check_if_ip_is_private(prev.ip_address, v4) and not check_if_ip_is_private(ip, v4):
						return_hops.append(((prev.ip_address, ip), 
						     (min(prev_ip_to_rtt[prev.ip_address]), current_rtt_min), 
						     (max(prev_ip_to_rtt[prev.ip_address]), current_rtt_max)))
						conditional_count += 1

			actual_count += len(ip_to_rtt)

			prev_item = item
			prev_ip_to_rtt = ip_to_rtt

	return return_hops, actual_count, conditional_count


def ripe_process_traceroutes (start_time, end_time, msm_id, ip_version, geolocation_validation=False, chunk_hours=2, resume=True):

	"""
	This function puts it all together
	(1) Get the raw traceroutes first
	(2) Process the traceroutes
	(3) Generate a dictionary with links and latencies

	Additionally save the results for every 12 hours

	Returns the generated dictionary
	"""

	save_directory = output_path('ripe_data')
	save_directory.mkdir(parents=True, exist_ok=True)
	state_file = _resume_state_file(save_directory, msm_id, ip_version, start_time, end_time)
	checkpoint_file = _resume_checkpoint_file(save_directory, msm_id, ip_version, start_time, end_time)

	time = start_time
	d = {}
	count = 0

	if resume and state_file.exists():
		with open(state_file, 'rb') as fp:
			state = pickle.load(fp)
		if state.get('completed') and Path(state.get('final_file', '')).exists():
			logger.info('RIPE measurement %s already completed for this window; loading %s', msm_id, state['final_file'])
			with open(state['final_file'], 'rb') as fp:
				return pickle.load(fp)
		if Path(state.get('checkpoint_file', '')).exists():
			logger.info('Resuming RIPE measurement %s from %s', msm_id, state['next_time'])
			with open(state['checkpoint_file'], 'rb') as fp:
				d = pickle.load(fp)
			time = state['next_time']
			count = state['count']

	if ip_version == 4:
		v4 = True 
	else:
		v4 = False 

	if geolocation_validation:
		ip_location_with_penalty_and_total_count = {}

		print (f'First loading probe to coordinate map')

		probe_to_coordinate_map = load_probe_location_result()

		print ('Loading all geolocation sources')

		maxmind_output, ripe_output, caida_output, iplocation_output = load_all_geolocation_info(ip_version)

		print ('Successfully loaded all geolocation results')


	while time < end_time:

		print ('Stage 1 : Loading/Downloading the data from RIPE Atlas')
		time_end = min(time + timedelta(hours=chunk_hours), end_time)
		traceroute_output, save_file = download_data_from_ripe_atlas(time, time_end, msm_id, 1)
		print (f'Length of raw traceroutes is {len(traceroute_output)}')

		print ('Stage 2 : Processing the data from RIPE Atlas')
		new_file = 'processed_' + '_'.join(save_file.name.split('_')[1:])
		parent_dir = save_file.parent
		processed_file = parent_dir / new_file
		updated_traceroute_output = process_transform_traceroute (traceroute_output, processed_file, 1)
		print (f'Length of processed traceroutes : {len(updated_traceroute_output)}')

		if geolocation_validation:

			print ('Stage 2.1: Performing SoL testing and validating locations')

			geolocation_sol_validation_ripe(updated_traceroute_output, probe_to_coordinate_map,
			        iplocation_output, maxmind_output,
			        ripe_output, caida_output,
			        ip_location_with_penalty_and_total_count, v4)

			print (f'Our current ip_location_with_penalty_and_total_count length is {len(ip_location_with_penalty_and_total_count)}')

			print (f'Lets save the current result')

			with open(str(output_path('location_data/ripe_validated_ip_locations_v{}_{}')).format(ip_version, msm_id), 'wb') as fp:
				pickle.dump(ip_location_with_penalty_and_total_count, fp, protocol=pickle.HIGHEST_PROTOCOL)

			print (f'Finished saving the results')


		print ('Stage 3 : Identifying the big jumps and storing in a dictionary')
		for index, traceroute in enumerate(updated_traceroute_output):
   
			ripe_hops, actual_ripe_hops, conditional_ripe_hops = get_ripe_hops(traceroute, v4)

			for a_ripe_hop in ripe_hops:

				ip_addresses = a_ripe_hop[0]
				all_latencies = d.get(ip_addresses, [])

				all_min_latencies = a_ripe_hop[1]
				all_max_latencies = a_ripe_hop[2]

				latency_min = round((all_min_latencies[1] - all_min_latencies[0]) / 2, 2)
				all_latencies.append(latency_min)
				d[ip_addresses] = all_latencies


		time = time_end

		print (f'Current count is {count} and dictionary length is {len(d)}')

		with open(checkpoint_file, 'wb') as fp:
			pickle.dump(d, fp, protocol=pickle.HIGHEST_PROTOCOL)

		with open(state_file, 'wb') as fp:
			pickle.dump({
			 'completed': False,
			 'count': count + 1,
			 'next_time': time,
			 'checkpoint_file': str(checkpoint_file),
			 'measurement': msm_id,
			 'ip_version': ip_version,
			 'chunk_hours': chunk_hours,
			}, fp, protocol=pickle.HIGHEST_PROTOCOL)

		if count % 6 == 0:
		    logger.info('Writing RIPE intermediate file for count %d', count // 6)
		    file_name = f'uniq_ip_dict_{msm_id}_all_links_v{ip_version}_min_all_latencies_only_' + str(count // 6)
		    save_file = parent_dir / file_name
		    with open(save_file, 'wb') as fp:
		        pickle.dump(d, fp, protocol=pickle.HIGHEST_PROTOCOL)


		count += 1

		print ()
		print ('*' * 50)
		print ()


	end_time_int = int(calendar.timegm(end_time.timetuple()))
	end_process_time = datetime.fromtimestamp(end_time_int, tz = timezone.utc).strftime("%m_%d_%Y_%H_%M")

	logger.info('Finishing RIPE processing, doing the last save')
	file_name = f'uniq_ip_dict_{msm_id}_all_links_v{ip_version}_min_all_latencies_only_{end_process_time}_count_' + str(count // 6)
	save_file = parent_dir / file_name
	with open(save_file, 'wb') as fp:
	    pickle.dump(d, fp, protocol=pickle.HIGHEST_PROTOCOL)

	with open(state_file, 'wb') as fp:
		pickle.dump({
		 'completed': True,
		 'count': count,
		 'next_time': end_time,
		 'checkpoint_file': str(checkpoint_file),
		 'final_file': str(save_file),
		 'measurement': msm_id,
		 'ip_version': ip_version,
		 'chunk_hours': chunk_hours,
		}, fp, protocol=pickle.HIGHEST_PROTOCOL)

	return d 


if __name__ == '__main__':

	start_time = datetime(2022, 3, 15, 0)
	end_time = datetime(2022, 3, 29, 0)

	# The measurement ids used are 5051 and 5151 for v4 and 6052 and 6152 for v6
	# The number (6) in example below indicates the IP version, which will be according to the measurement IDs
	# That number is mostly used for just saving the results

	result = ripe_process_traceroutes(start_time, end_time, '6052', 6, True)

	print (f'Result length is {len(result)}')
