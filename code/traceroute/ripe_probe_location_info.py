import subprocess, pickle
from pathlib import Path
from utils.project_paths import log_path, output_path, raw_path, result_path

def run_ripe_atlas_query_to_get_all_probe_locations():

	p = subprocess.Popen('ripe-atlas probe-search --all --status 1 --field id --field address_v4 --field coordinates', 
	                    shell=True, stdout=subprocess.PIPE)
	result = p.communicate()[0].decode()

	entry_list = result.split('\n')[3:-5]
	probe_entries = [tuple(item.split()) for item in entry_list]

	probe_to_coordinate_map = {}

	for item in probe_entries:
		lat_lon_tuple = tuple(map(float, item[2].split(',')))
		# -1111.0 is used to tag all probes for which location is unknown (these are typically not public probes)
		if -1111.0 not in lat_lon_tuple:
			probe_to_coordinate_map[item[0]] = (item[1], lat_lon_tuple)

	return probe_to_coordinate_map


def save_probe_location_result (probe_to_coordinate_map):

	with open(str(output_path('all_ripe_probes_ip_and_coordinates')), 'wb') as fp:
		pickle.dump(probe_to_coordinate_map, fp)


def load_probe_location_result():


	if Path(output_path('all_ripe_probes_ip_and_coordinates')).exists():
		with open(str(output_path('all_ripe_probes_ip_and_coordinates')), 'rb') as fp:
			probe_to_coordinate_map = pickle.load(fp)
	else:
		print ('File was missing, running the queries again')
		probe_to_coordinate_map = run_ripe_atlas_query_to_get_all_probe_locations()
		save_probe_location_result(probe_to_coordinate_map)

	return probe_to_coordinate_map


if __name__ == '__main__':

	probe_to_coordinate_map = run_ripe_atlas_query_to_get_all_probe_locations()

	print (f'We have results for {len(probe_to_coordinate_map)} probes and we are saving results now')

	save_probe_location_result(probe_to_coordinate_map)

	print ('Loading the results to verify')

	probe_to_coordinate_map = load_probe_location_result()

	print (f'We have results for {len(probe_to_coordinate_map)} probes')