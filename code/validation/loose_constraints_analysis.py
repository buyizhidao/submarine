import pickle, sys
from pathlib import Path
from collections import Counter
from utils.project_paths import log_path, output_path, raw_path, result_path

def load_all_required_files ():

	probe_to_measurement_map_file = 'validation/current_running_measurements_loose_constraints'

	if Path(probe_to_measurement_map_file).exists():
		with open(probe_to_measurement_map_file, 'rb') as fp:
			probe_to_measurement_map = pickle.load(fp)

		measurement_to_probe_map = {v:k for k,v in probe_to_measurement_map.items()}

	else:
		print (f'{probe_to_measurement_map_file} not found !!')
		sys.exit(1)

	link_to_probes_map_file = 'validation/select_probes_loose_constraints'

	if Path(link_to_probes_map_file).exists():
		with open(link_to_probes_map_file, 'rb') as fp:
			original_link_to_probes_map = pickle.load(fp)

		probe_to_original_link_map = {tuple(v):k for k,v in original_link_to_probes_map.items()}

	else:
		print (f'{link_to_probes_map_file} not found !!')
		sys.exit(1)

	latency_link_to_measurement_map_file = 'validation/high_latency_links_loose_constraints'

	if Path(latency_link_to_measurement_map_file).exists():
		with open(latency_link_to_measurement_map_file, 'rb') as fp:
			latency_link_to_measurement_map = pickle.load(fp)

		measurement_to_latency_link_map = {v['measurement']:k for k,v in latency_link_to_measurement_map.items()}

	else:
		print (f'{latency_link_to_measurement_map_file} not found !!')
		sys.exit(1)


	return probe_to_measurement_map, measurement_to_probe_map, original_link_to_probes_map, probe_to_original_link_map, latency_link_to_measurement_map, measurement_to_latency_link_map


def load_mapping_file ():

	mapping_file = str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v4'))

	if Path(mapping_file).exists():
		with open(mapping_file, 'rb') as fp:
			mapping = pickle.load(fp)

	else:
		print (f'{mapping_file} not found !!')
		sys.exit(1)

	return mapping


if __name__ == '__main__':

	probe_to_measurement_map, measurement_to_probe_map, original_link_to_probes_map, probe_to_original_link_map, latency_link_to_measurement_map, measurement_to_latency_link_map = load_all_required_files()

	mapping = load_mapping_file()

	print ('Finished loading the required files')

	exact_link_match = 0
	exact_cable_match = 0
	partial_cable_match = 0
	partial_match_1 = []
	partial_match_2 = []
	partial_common = []
	no_cable_match_same_country = 0
	no_cable_match_different_country = 0
	ignore_count = 0

	overlap = list(set(latency_link_to_measurement_map.keys()) & set(mapping.keys()))
	print (f'Overlap between latency link and our mapping : {len(overlap)}. Total latency links : {len(latency_link_to_measurement_map)}')

	print ('Loading ip to country cluster map')
	with open(str(output_path('mapping_outputs/geolocation_country_cluster_sol_validated_v4')), 'rb') as fp:
		country_mapping = pickle.load(fp)
	print ('Finished loading country mapping')

	for count, (latency_link, value) in enumerate(latency_link_to_measurement_map.items()):
		if latency_link:
			print (f'Latency link : {latency_link}')
			measurement = value['measurement']
			print (f'Measurement ID : {measurement}')
			probe = measurement_to_probe_map[measurement]
			print (f'Probes used : {probe}')
			original_link = probe_to_original_link_map[probe]
			print (f'Original link : {original_link}')

			if original_link == latency_link:
				exact_link_match += 1
				print (f'Exact link match found')

			else:
			 # Checking if latency link is in our mapping
				if latency_link in overlap:
					mapping_latency_link = mapping.get(latency_link, None)
					mapping_original_link = mapping.get(original_link)

					if mapping_original_link and mapping_latency_link:

						if mapping_original_link[1] == mapping_latency_link[1]:
							exact_cable_match += 1
							print (f'Exact cables matched : {mapping_original_link[0]}')

						else:
						 # Let's check if there is any overlap of cables
							overlap_cables = list(set(mapping_original_link[1]) & set(mapping_latency_link[1]))
							if len(overlap_cables) > 0:
							 # checking if top cable predictions are the same
								if mapping_original_link[1][0] == mapping_latency_link[1][0]:
									exact_cable_match += 1
								else:
									partial_cable_match += 1
									min_1 = min([mapping_original_link[1].index(item) for item in overlap_cables])
									min_2 = min([mapping_latency_link[1].index(item) for item in overlap_cables])
									partial_match_1.append(min_1)
									partial_match_2.append(min_2)
									omin = min([max(mapping_original_link[1].index(item), mapping_latency_link[1].index(item)) for item in overlap_cables])
									partial_common.append(omin)
								print (f'Cables for original: {mapping_original_link[1]}, latency link: {mapping_latency_link[1]} and matched cables are : {overlap_cables}')
							else:
								if len(mapping_latency_link[1]) > 0 and len(mapping_original_link[1]) > 0:
								 # Taking the top country pairs
									original_link_country = (country_mapping[original_link[0]][0][0], country_mapping[original_link[1]][0][0])
									latency_link_country = (country_mapping[latency_link[0]][0][0], country_mapping[latency_link[1]][0][0])
									if original_link_country == latency_link_country:
										no_cable_match_same_country += 1
									else:
										no_cable_match_different_country += 1
         # no_cable_match += 1
									print (f'No match: Cables for original: {mapping_original_link[1]}, latency link: {mapping_latency_link[1]}')
								else:
									ignore_count += 1
									print (f'Looks like no mapping was made. Cables for original: {mapping_original_link[1]}, latency link: {mapping_latency_link[1]}')

			print ('*' * 50)

	print (f'Final results:\nExact link match: {exact_link_match}\nExact cable match: {exact_cable_match}\nPartial cable match: {partial_cable_match}\nNo cable match (same country): {no_cable_match_same_country}\nNo cable match (different country): {no_cable_match_different_country}\nIgnore: {ignore_count}\n')
	print (f'Min1 counter: {Counter(partial_match_1)}')
	print (f'Min2 counter: {Counter(partial_match_2)}')
	print (f'Min common counter: {Counter(partial_common)}')
	print (f'Overlap between latency link and our mapping : {len(overlap)}. Total latency links : {len(latency_link_to_measurement_map)}')



