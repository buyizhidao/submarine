import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

import pickle
from pathlib import Path
from location.ipgeolocation_utils import Location

def generate_split_for_parallel_processing (ip_version=4, exclude_files=[], single_file_length = 4500):

	with open(str(output_path('mapping_outputs/all_ips_v{}')).format(ip_version), 'rb') as fp:
		all_ips = pickle.load(fp)

	print (f'We have {len(all_ips)} IPs in total')

	ips_to_process = set(all_ips)

	if len(exclude_files) > 0:
		for file in exclude_files:
			with open(file, 'rb') as fp:
				exclude = pickle.load(fp)

			ips_to_process = ips_to_process.difference(set(exclude.keys()))

	ips_to_process = list(ips_to_process)

	print (f'We have to load geolocation info for {len(ips_to_process)} IPs')

	max_files = (len(ips_to_process) // single_file_length) + 1

	save_directory = output_path('ip_data')

	for file_num in range(max_files):
		if file_num == (max_files - 1):
			ips = ips_to_process[(file_num * single_file_length):]
		else:
			ips = ips_to_process[(file_num * single_file_length): ((file_num + 1)* single_file_length)]

		save_file = 'ips_group_{}'.format(file_num)

		with open(save_directory / save_file, 'wb') as fp:
			pickle.dump(ips, fp)

		print (f'Current file {save_file} has {len(ips)} entries')


if __name__ == '__main__':

	generate_split_for_parallel_processing(ip_version=6, exclude_files=['individual_source_combined_results/iplocation_geolocation_v6'])