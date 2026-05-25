import pickle
from pathlib import Path
from utils.project_paths import log_path, output_path, raw_path, result_path

def load_cable_mapping_output (ip_version=4):

	with open(str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v{}')).format(ip_version), 'rb') as fp:
		cable_mapping = pickle.load(fp)

	return cable_mapping


def number_of_cables_and_landing_points_mapped (cable_mapping):

	all_cables = []
	all_landing_points = []
	count = 0

	for link, mapping in cable_mapping.items():
		all_cables.extend(mapping[1])
		if len(mapping[1]) == 0:
			count += 1
		for cable_landing_points in mapping[-2]:
			for landing_points in cable_landing_points:
				all_landing_points.extend(landing_points)


	uniq_cables = list(set(all_cables))

	print (f'We have mapping for {len(uniq_cables)} cables')

	uniq_landing_points = list(set(all_landing_points))

	print (f'We have mapping for {len(uniq_landing_points)} landing points')

	print (f'We have mapping for {(1 - (count/len(cable_mapping))) * 100} links')


if __name__ == '__main__':

	cable_mapping = load_cable_mapping_output()
	number_of_cables_and_landing_points_mapped(cable_mapping)

