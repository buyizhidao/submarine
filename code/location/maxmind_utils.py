from pathlib import Path

import pickle

from collections import namedtuple

import geoip2.database
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import get_logger

MaxmindLocation = namedtuple('MaxmindLocation', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network'])

logger = get_logger(__name__)


def save_maxmind_output(maxmind_location, ip_version=4, tags='default'):

	with open(str(output_path('location_data/maxmind_location_output_v{}_{}')).format(ip_version, tags), 'wb') as fp:
		pickle.dump(maxmind_location, fp)


def _get_name(value):
	try:
		return value.names['en']
	except:
		try:
			return value.name
		except:
			return None


def _get_trait(response, attr):
	try:
		return getattr(response.traits, attr)
	except:
		return None


def generate_locations_for_list_of_ips (ips_list, ip_version=4, tags='default', mmdb_file=str(raw_path('location_data/GeoLite2-City.mmdb'))):

	maxmind_location = {}

	skipped_ips = []

	# Checking presence of mmdb file
	if Path(mmdb_file).exists():
		with geoip2.database.Reader(mmdb_file) as reader:
			for count, ip_address in enumerate(ips_list):

				try:
					response = reader.city(ip_address)
				except:
					skipped_ips.append(ip_address)
					continue

				city = _get_name(response.city)

				try:
					subdivisions = _get_name(response.subdivisions[0])
				except:
					subdivisions = None

				country = _get_name(response.country)

				location = MaxmindLocation(city, subdivisions, country,
				       response.location.accuracy_radius, 
				       response.location.latitude, 
				       response.location.longitude, 
				       _get_trait(response, 'autonomous_system_number'), 
				       _get_trait(response, 'network'))

				maxmind_location[ip_address] = location

		save_maxmind_output(maxmind_location, ip_version)

		return (maxmind_location, skipped_ips)

	else:
		logger.error('File not found. The mmdb file should be saved as %s', mmdb_file)
		return (None, None)


def load_maxmind_output(ip_version=4, tags='default', ips_list=[]):


	file_locations = [
	 str(output_path('location_data/maxmind_location_output_v{}_{}')).format(ip_version, tags),
	 str(output_path('location_data/maxmind_location_ouput_v{}_{}')).format(ip_version, tags),
	]

	for file_location in file_locations:
		if Path(file_location).exists():
			with open(file_location, 'rb') as fp:
				maxmind_location = pickle.load(fp)
			return maxmind_location

	if len(ips_list) > 0:
		maxmind_location, _ = generate_locations_for_list_of_ips(ips_list)
	else:
		logger.error('Please enter either valid file tag or ips list')
		return None

	return maxmind_location


if __name__ == '__main__':

 # sample_ips_list = ['66.85.82.9', '156.225.182.1', '67.59.254.241', '103.78.227.1', '193.34.197.140', '23.111.226.1', '193.0.214.1', '152.255.147.235', '216.19.218.1']

	ip_version = 6

	with open(str(output_path(f'mapping_outputs/all_ips_v{ip_version}')), 'rb') as fp:
		sample_ips_list = pickle.load(fp)

	maxmind_location, skipped_ips = generate_locations_for_list_of_ips(sample_ips_list, ip_version)

	logger.info('We got results for %d IPs and missed %d IPs', len(maxmind_location), len(skipped_ips))
