import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

import pickle, json
from datetime import datetime, timezone, timedelta
from traceroute.ripe_traceroute_utils import ripe_process_traceroutes

from collections import namedtuple, Counter
LandingPoints = namedtuple('LandingPoints', ['latitude', 'longitude', 'country', 'location', 'cable'])

def construct_landing_point_location_to_id_dict():

	"""
	As all the landing point data is stored in ID format, and for our tests we need to compare with
	actual locations, let's get the required reverse mapping
	"""

	with open(str(raw_path('submarine_data/landing_points_dict')), 'rb') as fp:
		landing_points_dict = pickle.load(fp)

	reverse_landing_points_dict = {v.location : k for k,v in landing_points_dict.items()}

	forward_landing_points_dict = {k : v.location for k,v in landing_points_dict.items()}

	return reverse_landing_points_dict, forward_landing_points_dict


def get_latest_mapping_results():

	"""
	Loads and returns the latest link to cable mapping results
	"""

	with open(str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v4')), 'rb') as fp:
		mapping = pickle.load(fp)

	return mapping


def get_latest_category_mapping_results():

	"""
	Loads and returns the latest category mapping results
	"""

	with open(str(result_path('mapping_outputs/categories_map_sol_validated_updated_v4')), 'rb') as fp:
		category_mapping = pickle.load(fp)

	return category_mapping


def local_update (existing_dict, to_be_merged_dict):

	overlap = list(set(existing_dict.keys()) & set(to_be_merged_dict))

	return_dict = to_be_merged_dict.copy()

	return_dict.update(existing_dict)

	for k in overlap:
		new_data = to_be_merged_dict.get(k, [])
		old_data = existing_dict.get(k, [])
		return_dict[k] = old_data + new_data

	return return_dict


def get_ripe_data_for_given_end_date (end_date, download=False):

	"""
	Returns the ripe data (both 5051 & 5151) collected over that specified end date
	Inputs:
		end_data should be in "mm_dd_yyyy" format
	"""

	if download:
		month, date, year = (int(item) for item in end_date.split('_'))
		end_time = datetime(year, month, date, 0)
		start_time = end_time - timedelta(days=2)

		ripe_process_traceroutes(start_time, end_time, '5051', 4, False)
		ripe_process_traceroutes(start_time, end_time, '5151', 4, False)

	directory = str(output_path('ripe_data'))

	all_data = {}

	for file in os.listdir(directory):
		if end_date in file:
			matched_file = directory + '/' + file
			with open(matched_file, 'rb') as fp:
				ripe_data = pickle.load(fp)

			all_data = local_update(all_data, ripe_data)

	if len(all_data) == 0:
		print (f'Required files for the dates not generated, needs to be done manually')

	return all_data


def get_matched_links_for_given_conditions (mapping, reverse_landing_points_dict, selected_landing_point, cable_name=None, only_cable=False):

 # matched_links = []
	matched_links = {}

	if (not cable_name) and only_cable:
		print ('Enter the cable that needs to be checked')
		return None

	for key, value in mapping.items():
  
		cables = value[1]
		landing_points = value[3]

		if (not cable_name) or (cable_name in cables):

		 # If we are matching for the link to only have a single cable, we just check after the earlier match is for
		 # the link we have mapped only a single cable (and that was what was matched with our query)

			if only_cable and len(cables) != 1:
				continue

			for cable_all_possible_landing_points in landing_points:
				for landing_point_tuples in cable_all_possible_landing_points:
					if reverse_landing_points_dict[selected_landing_point] in landing_point_tuples:
					 # matched_links.append(key)
						matched_links[key] = value
						break


	return matched_links


def get_matched_links_categories (matched_links, category_mapping):

	categories_to_matched_links = {}
	matched_links_to_categories = {}

	for category, links in category_mapping.items():
		overlap = list(set(matched_links.keys()) & set(links))
		if len(overlap) > 0:
			categories_to_matched_links[category] = overlap

 # Just the reverse mapping with each link assigned to it's category
	matched_links_to_categories = {i : k for k,v in categories_to_matched_links.items() for i in v}

	return (categories_to_matched_links, matched_links_to_categories)


if __name__ == '__main__':

	end_dates = ['01_21_2022', '01_24_2022', '01_27_2022'] # Yemen

	cable = None # Yemen
	# cable = 'Kumul Domestic Submarine Cable System'

	landing_point = 'Al Hudaydah, Yemen'
	# landing_point = 'Madang, Papua New Guinea'

	reverse_landing_points_dict, forward_landing_points_dict = construct_landing_point_location_to_id_dict()

	print ('Loading the mapping results')

	mapping = get_latest_mapping_results()

	print ('Finished loading the mapping results')

	print ('Loading the category mapping results')

	category_mapping = get_latest_category_mapping_results()

	print ('Finished loading the category mapping results')

	print ('Getting the matched links')

	matched_links = get_matched_links_for_given_conditions(mapping, reverse_landing_points_dict, landing_point, cable)

	print (f'Total matched links : {len(matched_links)}')

	categories_to_matched_links, matched_links_to_categories = get_matched_links_categories(matched_links, category_mapping)

	for date in end_dates:

		print ('*' * 50)

		ripe_data = get_ripe_data_for_given_end_date(date, True)

		print (f'End date : {date}')

		overlap = list(set(matched_links.keys()) & set(ripe_data))

		print ('#' * 25)

		# Getting the overlapped links count and sorting them based on the count #
		count_of_links_dict_unsorted = {item: len(ripe_data[item]) for item in overlap}
		count_of_links_dict = {k: v for k,v in sorted(count_of_links_dict_unsorted.items(), key=lambda x: x[1], reverse=True)}

		# Getting the categories for the overlapped links with count
		final_results_dict = {}
		overlapped_categories_count = {}
		avg_mapped_cable_count_per_link = 0
		all_landing_points = []
		avg_score = 0

		for link, count in count_of_links_dict.items():
   
			category = matched_links_to_categories[link]
			link_mapping_results = matched_links[link][1]
			best_score = matched_links[link][2][0]
			best_landing_point_pairs = (forward_landing_points_dict[matched_links[link][3][0][0][0]], forward_landing_points_dict[matched_links[link][3][0][0][1]])
			current_category_count = overlapped_categories_count.get(category, 0)

			final_results_dict[link] = {
			        'count' : count, 
			        'category' : category, 
			        'cable count for link' : len(link_mapping_results), 
			        'cables mapped' : link_mapping_results,
			        'best_score': best_score,
			        'best_landing_point_pairs': best_landing_point_pairs
			       }
          
			overlapped_categories_count[category] = current_category_count + 1
			avg_mapped_cable_count_per_link += len(link_mapping_results)
			avg_score += best_score
			all_landing_points.append(best_landing_point_pairs)

		avg_mapped_cable_count_per_link /= len(overlap)
		avg_score /= len(overlap)

		print_final_results_dict = {str(k): v for k, v in final_results_dict.items()}

		#for item in overlap:
		#	print (f'{item}: {len(ripe_data[item])}')

		print ('Final results \n')

		print (json.dumps(print_final_results_dict, indent=4))

		print ()

		print ('Category results \n')

		print (json.dumps(overlapped_categories_count, indent=4))

		print ()

		print (f'Average cables mapped per link is {avg_mapped_cable_count_per_link}')

		print ('#' * 25)

		print (f'We had an overlap of {len(overlap)} for {date}')

		print ('*' * 50)

		print (f'The average score we have is {avg_score}')

		print ('*' * 50)

		print (f'The common landing points are {Counter(all_landing_points)}')
