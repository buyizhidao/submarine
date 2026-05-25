import pickle
from pathlib import Path
from utils.project_paths import log_path, output_path, raw_path, result_path

def load_rtt_proximity_ground_truth_data ():

	with open(str(raw_path('ip_data/RTT-Proximity-4839-DNS-based-11857-GT.txt')), 'r') as fp:
		file_contents = fp.readlines()

	ip_contents = [item.split(',') for item in file_contents if len(item.split(',')) > 0]
	ip_to_location = {v[1]: (float(v[2]), float(v[3])) for v in ip_contents if len(v) > 1}

	with open(str(output_path('ip_data/ip_to_location_ground_truth')), 'wb') as fp:
		pickle.dump(ip_to_location, fp)

	return ip_to_location


def generate_split_files_for_parallel_processing(single_file_length=4500):

	ip_to_location = load_rtt_proximity_ground_truth_data()

	all_ips = list(ip_to_location.keys())

	max_files = (len(all_ips) // single_file_length) + 1

	save_directory = output_path('ip_data')

	for file_num in range(max_files):
		if file_num == (max_files - 1):
			ips = all_ips[(file_num * single_file_length):]
		else:
			ips = all_ips[(file_num * single_file_length): ((file_num + 1)* single_file_length)]

		save_file = 'ips_group_{}'.format(file_num)

		with open(save_directory / save_file, 'wb') as fp:
			pickle.dump(ips, fp)

		print (f'Current file {save_file} has {len(ips)} entries')



if __name__ == '__main__':

	generate_split_files_for_parallel_processing()