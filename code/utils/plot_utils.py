import pickle, re
from pathlib import Path

import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

def load_final_cable_mapping_files(mode=2, ip_version=4):

	save_directory = result_path('mapping_outputs')

	link_to_cable_score_mapping, link_to_cable_score_mapping_sol_validated = {}, {}
 
	if mode in [0, 2]:
		save_file = 'link_to_cable_and_score_mapping_v{}'.format(ip_version)
		if Path(save_directory/save_file).exists():
			with open(save_directory/save_file, 'rb') as fp:
				link_to_cable_score_mapping = pickle.load(fp)
		else:
			print (f'Required final cable mapping file not found. Generate it!!!')
			sys.exit(1)

	if mode in [1, 2]:
		save_file = 'link_to_cable_and_score_mapping_sol_validated_v{}'.format(ip_version)
		if Path(save_directory/save_file).exists():
			with open(save_directory/save_file, 'rb') as fp:
				link_to_cable_score_mapping_sol_validated = pickle.load(fp)
		else:
			print (f'Required final cable mapping file not found. Generate it!!!')
			sys.exit(1)

	return link_to_cable_score_mapping, link_to_cable_score_mapping_sol_validated



def load_final_category_map_files(mode=2, ip_version=4):

	save_directory = result_path('mapping_outputs')

	categories_map, categories_map_sol_validated = {}, {}
 
	if mode in [0, 2]:
		save_file = 'categories_map_updated_v{}'.format(ip_version)
		if Path(save_directory/save_file).exists():
			with open(save_directory/save_file, 'rb') as fp:
				categories_map = pickle.load(fp)
		else:
			print (f'Required categroy mapping file not found. Generate it!!!')
			sys.exit(1)

	if mode in [1, 2]:
		save_file = 'categories_map_sol_validated_updated_v{}'.format(ip_version)
		if Path(save_directory/save_file).exists():
			with open(save_directory/save_file, 'rb') as fp:
				categories_map_sol_validated = pickle.load(fp)
		else:
			print (f'Required category mapping file not found. Generate it!!!')
			sys.exit(1)

	return categories_map, link_to_cable_score_mapping_sol_validated



def generate_text_files_for_score_and_count_plotting_helper (link_to_cable_score_mapping, tags='', ip_version=4):

	score_map = {'bg_oc': [], 'og_oc': [], 'bb_oc': [],
	      'bg_te': [], 'og_te': [], 'bb_te': []}

	cable_count_map = {'bg_oc': {}, 'og_oc': {}, 'bb_oc': {},
	        'bg_te': {}, 'og_te': {}, 'bb_te': {}}

	for link, scores in link_to_cable_score_mapping.items():
		category = scores[-1]
  
		# For the score generation part
		# We will just collect the scores for non-zero values
		if isinstance(scores[2], list):
			if len(scores[2]) != 0:
				score_map[category].append(round(max(scores[2]), 2))
		else:
			if scores[2] != 0:
				score_map[category].append(round(scores[2], 2))

  # For the cable count generation part
		cable_count = len(scores[1])
		if cable_count == 0:
			pass
		elif 1 <= cable_count <= 2:
			current_count = cable_count_map[category].get(str(cable_count), 0)
			current_count += 1
			cable_count_map[category][str(cable_count)] = current_count
		elif cable_count > 10:
			current_count = cable_count_map[category].get('>10', 0)
			current_count += 1
			cable_count_map[category]['>10'] = current_count
		elif 3 <= cable_count <= 5:
			current_count = cable_count_map[category].get('3-5', 0)
			current_count += 1
			cable_count_map[category]['3-5'] = current_count
		else:
			current_count = cable_count_map[category].get('6-10', 0)
			current_count += 1
			cable_count_map[category]['6-10'] = current_count

 # Now let's write the outputs to a file
	save_directory = Path.cwd() / 'plot_results'
	save_directory.mkdir(parents=True, exist_ok=True)

	all_scores_file = 'all_scores_{}v{}.txt'.format(tags, ip_version)

	for category, scores in score_map.items():
		file = '{}_{}v{}.txt'.format(category, tags, ip_version)
  
		# Writing to individual category file
		with open(save_directory/file, 'w') as f:
			for single_link_score in scores:
				if single_link_score != 0:
					f.write(str(single_link_score)+'\n')

  # Writing to all categories file
		with open(save_directory/all_scores_file, 'a') as f:
			for single_link_score in scores:
				if single_link_score != 0:
					f.write(str(single_link_score)+'\n')

	cable_count_list = {}
	for category, content in cable_count_map.items():
		for count_key, total_count in content.items():
			current_list = cable_count_list.get(count_key, [])
			current_list.append(total_count)
			cable_count_list[count_key] = current_list

	file = 'all_count_{}v{}.dat'.format(tags, ip_version)

	with open(save_directory/file, 'w') as f:
		keys = 'N ' + ' '.join(list(cable_count_map.keys()))
		f.write(keys+'\n')
		for count_key, counts in sorted(cable_count_list.items(), key=lambda x: int(re.search(r'\d+', x[0]).group())):
			string = count_key + ' ' + ' '.join(map(str, counts))
			f.write(string+'\n')



def generate_text_files_for_score_and_count_plotting(mode=2, ip_version=4, tags=''):

	link_to_cable_score_mapping, link_to_cable_score_mapping_sol_validated = load_final_cable_mapping_files(mode=mode, ip_version=ip_version)

	if mode in [0, 2]:
		generate_text_files_for_score_and_count_plotting_helper(link_to_cable_score_mapping, tags=tags, ip_version=ip_version)

	if mode in [1, 2]:
		tags = 'sol_validated_' + tags
		generate_text_files_for_score_and_count_plotting_helper(link_to_cable_score_mapping_sol_validated, tags=tags, ip_version=ip_version)



if __name__ == '__main__':

	generate_text_files_for_score_and_count_plotting(mode=1, ip_version=4, tags='541_')
