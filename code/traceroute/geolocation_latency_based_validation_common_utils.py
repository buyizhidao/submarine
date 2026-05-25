import pickle, json
from collections import namedtuple
from haversine import haversine, Unit
from utils.project_paths import log_path, output_path, raw_path, result_path

# Later update these 2 to directly take from geolocation files (under location/)
Location = namedtuple('Location', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network', 'ISP', 'Org'])
MaxmindLocation = namedtuple('MaxmindLocation', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network'])

def load_all_geolocation_info(ip_version=4, tags='default'):

	print ('First, we are loading the outputs from maxmind')

	with open(str(output_path('location_data/maxmind_location_output_v{}_{}')).format(ip_version, tags), 'rb') as fp:
		maxmind_output = pickle.load(fp)

	print (f'From Maxmind, we got results for {len(maxmind_output)} IPs')

	print ('Next, we will load the geolocation results from RIPE IPMap')

	with open(str(output_path('location_data/ripe_location_output_v{}_{}')).format(ip_version, tags), 'rb') as fp:
		ripe_output = pickle.load(fp)

	print (f'From RIPE IPMap, we got results for {len(ripe_output)} IPs')


	if ip_version == 4:
		print ('Next, we will load the geolocation results from CAIDA')

		with open(str(output_path('location_data/caida_location_output_{}')).format(tags), 'rb') as fp:
			caida_output = pickle.load(fp)

		print (f'From CAIDA, we got results for {len(caida_output)} IPs')
	else:
		caida_output = {}

	print ('Finally, we will load the geolocation results from other sources')

	with open(str(output_path('location_data/iplocation_location_output_v{}_{}')).format(ip_version, tags), 'rb') as fp:
		iplocation_output = pickle.load(fp)

	print (f'From other sources, we got results for {len(iplocation_output)} IPs')

	return (maxmind_output, ripe_output, caida_output, iplocation_output)



def extract_latlon_and_perform_sol_test (location, initial_lat_lon, rtt, index=0):

	try:
		if index <= 7:
			latitude = float(location.latitude.decode())
			longitude = float(location.longitude.decode())
		elif index == 8:
			latitude = location.latitude
			longitude = location.longitude
		elif index == 9:
			latitude = float(location[2])
			longitude = float(location[3])
		elif index == 10:
			latitude = float(location[3])
			longitude = float(location[4])

  # Performing SoL test
		distance = haversine(initial_lat_lon, (latitude, longitude))
		min_latency = distance * 1000 / 200000

		if min_latency > (rtt / 2):
		 # stats[index].append(1)
			return (False, (latitude, longitude))
		else:
		 # stats[index].append(0)
			return (True, (latitude, longitude))

	except:
		return (False, (None, None))



def fill_locations_dict_scores (prev_examined_location, status, 
        latitude, longitude,
        ip, ind, 
        ip_location_with_penalty_and_total_count):
 
 # Same things are repeated below (partially) to ensure that we don't add error if something goes out of expectation at the cost of losing data

 # First checking validity of latitude and longitude
	if latitude and longitude:
	 # If previous examined, it means we already populated the dict, now we just need to update the scores
		if prev_examined_location:
			current_contents = ip_location_with_penalty_and_total_count.get(ip, None)

			if not status:
			 # We failed SoL test for this location, let's add 1 to penalty
				current_contents['penalty_count'][ind] += 1

   # By default, we always increment the total count
			current_contents['total_count'][ind] += 1

			ip_location_with_penalty_and_total_count[ip] = current_contents

		else:

		 # We need to add these to the original dictionary, we have 11 geolocation sources

			current_contents = ip_location_with_penalty_and_total_count.get(ip,
			     {'location_index': [], 'coordinates': [],
			     'penalty_count': [0] * 11, 'total_count': [0] * 11})

			# Add only if this location source hasn't been added earlier
			if ind not in current_contents['location_index']:
				current_contents['location_index'].append(ind)
				current_contents['coordinates'].append((latitude, longitude))

				if not status:
					current_contents['penalty_count'][ind] += 1

				current_contents['total_count'][ind] += 1

				ip_location_with_penalty_and_total_count[ip] = current_contents
   
			else:
				print (f'This should never be printed. Examine what happened !!')



def compute_geolocation_performance (file, thresold=0.01):

	with open(file, 'rb') as fp:
		file_contents = pickle.load(fp)

 
	hard_count_stats = [sum(x) for x in zip(*[item['penalty_count'] for item in file_contents.values()])]
	total_count = [sum(x) for x in zip(*[item['total_count'] for item in file_contents.values()])]
	stats = [[], [], [], [], [], [], [], [], [], [], []]

	for value in file_contents.values():
		for index, penalty_count in enumerate(value['penalty_count']):
			if value['total_count'][index] > 0:
				if (penalty_count/value['total_count'][index]) <= thresold:
					stats[index].append(0)
				else:
					stats[index].append(1)

	print (f'Printing the stats now')

	hard_count_result = {index: value/total_count[index] for index, value in enumerate(hard_count_stats)}

	print ('Hard count stats are :')

	print (json.dumps(hard_count_result, indent=4))

	individual_ip_result = {index: sum(value)/len(value) for index, value in enumerate(stats)}

	print ('Individual IP geolocation stats are : ')

	print (json.dumps(individual_ip_result, indent=4))
 