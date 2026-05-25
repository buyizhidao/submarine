from pathlib import Path

import time, pickle
from utils.project_paths import log_path, output_path, raw_path, result_path

def save_caida_geolocation_output(caida_location, tags='default'):

	with open(str(output_path('location_data/caida_location_output_{}')).format(tags), 'wb') as fp:
		pickle.dump(caida_location, fp)


def get_node_to_geolocation_map():

	ip_to_geo_map_path = str(output_path('location_data/caida_ip_to_geo_map'))

	if Path(ip_to_geo_map_path).exists():
		print (f'IP to Geo map already generated, just loading it now')
		with open(ip_to_geo_map_path, 'rb') as fp:
			ip_to_geo_dict = pickle.load(fp)
		return ip_to_geo_dict
 
	else:
		midar_iff_nodes_file_path = str(output_path('location_data/midar-iff.nodes'))
		caida_nodes_to_geo_file_path = str(output_path('location_data/midar-iff.nodes.geo'))

		if Path(midar_iff_nodes_file_path).exists() and Path(caida_nodes_to_geo_file_path).exists():
   
			print ('Loading the midar-iff.node file first for processing')
			with open(midar_iff_nodes_file_path) as fp:
				contents = fp.readlines()

   # Figuring out the line where relevant info starts
			for index, line in enumerate(contents):
				if 'node N1' in line:
					start_index = index
					break

			updated_content = [line.split() for line in contents[start_index:]]
			nodes_to_ip_dict = {line[1].strip(':'): line[2:] for line in updated_content}

			del (contents)
			del (updated_content)

			print ('Loading midar-iff.nodes.geo file for porcessing')
			with open(caida_nodes_to_geo_file_path) as fp:
				contents = fp.readlines()

   # Figuring out the line where relevant info starts
			for index, line in enumerate(contents):
				if 'node.geo N' in line:
					start_index = index
					break

			updated_content = [line.split('\t') for line in contents[start_index:]]
			nodes_to_geo_dict = {line_parts[0].split()[-1].strip(':'): (line_parts[1], line_parts[2], line_parts[4], line_parts[5], line_parts[6], line_parts[9].strip()) for line_parts in updated_content}

			del(contents)
			del(updated_content)

			print ('Merging the results to get IP to Geo map')

			ip_to_geo_dict = {}

			for key in nodes_to_geo_dict:
				for ip in nodes_to_ip_dict[key]:
					ip_to_geo_dict[ip] = nodes_to_geo_dict[key]

			del(nodes_to_ip_dict)
			del(nodes_to_geo_dict)

			print ('Saving the results for future loading')

			with open(ip_to_geo_map_path, 'wb') as fp:
				pickle.dump(ip_to_geo_dict, fp, protocol=pickle.HIGHEST_PROTOCOL)

			return ip_to_geo_dict

		else:
			print (f'Required midar-iff.nodes and midar-iff.nodes.geo file not found')
			print (f'Download from CAIDA Ark and place it at ../data/intermediate/location_data')
			return None


def generate_location_for_list_of_ips (ips_list, tags='default'):

 # First we get to ip to geo mapping from CAIDA
	ip_to_geo_dict = get_node_to_geolocation_map()

	caida_location = {}

	for ip in ips_list:
		geolocation = ip_to_geo_dict.get(ip, None)
		if geolocation:
			caida_location[ip] = geolocation

	save_caida_geolocation_output(caida_location)

	return caida_location


def load_caida_geolocation_output (tags='default', ips_list = []):

	file_location = str(output_path('location_data/caida_location_output_{}')).format(tags)

	if Path(file_location).exists():
		with open(file_location, 'rb') as fp:
			caida_location = pickle.load(fp)

	else:
		if len(ips_list) > 0:
			caida_location = generate_location_for_list_of_ips(ips_list)
		else:
			print (f'Please enter either valid file tag or ips list')
			return None

	return caida_location


if __name__ == '__main__':

 #sample_ips_list = ['66.85.82.9', '156.225.182.1', '67.59.254.241', '103.78.227.1', '193.34.197.140', '23.111.226.1', '193.0.214.1', '152.255.147.235', '216.19.218.1']

	ip_version = 6

	with open(str(output_path(f'mapping_outputs/all_ips_v{ip_version}')), 'rb') as fp:
		sample_ips_list = pickle.load(fp)

	caida_location = generate_location_for_list_of_ips(sample_ips_list)

	print (f'We got results for {len(caida_location)} IPs')