import csv, pickle
from pathlib import Path 
from utils.project_paths import log_path, output_path, raw_path, result_path

def save_ripe_location_output(ripe_location, ip_version = 4, tags='default'):

	with open(str(output_path('location_data/ripe_location_output_v{}_{}')).format(ip_version, tags), 'wb') as fp:
		pickle.dump(ripe_location, fp)


def get_ripe_ip_to_location_map():

	ripe_ipmap_files_path = str(output_path('location_data/ripe_ipmap_files'))

	individual_file_contents = []
	total_count = 0
	file_count = 0

	if Path(ripe_ipmap_files_path).exists():
  
		for path in Path(ripe_ipmap_files_path).iterdir():
			if path.is_file() and 'csv' in str(path):
				d = {}
				with open(path, 'r') as fp:
					csv_reader = csv.reader(fp)
					for row in csv_reader:
						d[row[0].split('/')[0]] = (row[-6], row[-5], row[-3], row[-2], row[-1])
    
				individual_file_contents.append(d)
				file_count += 1
				total_count += len(d)

		if len(individual_file_contents) > 0:
   
			ripe_ip_to_location_map = {}
			for item in individual_file_contents:
				ripe_ip_to_location_map.update(item)

			return ripe_ip_to_location_map
  
		else:
			print ('Download the required files from "https://ftp.ripe.net/ripe/ipmap/" and save them as ../data/intermediate/location_data/ripe_ipmap_files')
			return None

	else:
		print ('Download the required files from "https://ftp.ripe.net/ripe/ipmap/" and save them as ../data/intermediate/location_data/ripe_ipmap_files')
		return None



def generate_location_for_list_of_ips_ripe (ips_list, ip_version=4, tags='default'):

 # First, we will get ip to geo mapping RIPE IPMap
	ripe_ip_to_location_map = get_ripe_ip_to_location_map()

	ripe_location = {}

	for ip in ips_list:
		geolocation = ripe_ip_to_location_map.get(ip, None)
		if geolocation:
			ripe_location[ip] = geolocation

	save_ripe_location_output(ripe_location, ip_version)

	return ripe_location



def load_ripe_geolocation_output (ip_version=4, tags='default', ips_list=[]):
 
	file_location = str(output_path('location_data/ripe_location_output_v{}_{}')).format(ip_version, tags)

	if Path(file_location).exists():
		with open(file_location, 'rb') as fp:
			ripe_location = pickle.load(fp)

	else:
		if len(ips_list) > 0:
			ripe_location = generate_location_for_list_of_ips_ripe(ips_list, ip_version)
		else:
			print (f'Please enter either valid file tag or ips list')
			return None

	return ripe_location



if __name__ == '__main__':

 #sample_ips_list = ['66.85.82.9', '156.225.182.1', '67.59.254.241', '103.78.227.1', '193.34.197.140', '23.111.226.1', '193.0.214.1', '152.255.147.235', '216.19.218.1']

	ip_version = 6

	with open(str(output_path(f'mapping_outputs/all_ips_v{ip_version}')), 'rb') as fp:
		sample_ips_list = pickle.load(fp)

	ripe_location = generate_location_for_list_of_ips_ripe(sample_ips_list, ip_version)

	print (f'We got results for {len(ripe_location)} IPs')
