import sys
from pathlib import Path
sys.path.insert(1, str(Path(__file__).resolve().parents[3]))
import Querying_Database as qdb
import pickle
from pathlib import Path
from collections import Counter
import Standardize_Locations
from utils.project_paths import log_path, output_path, raw_path, result_path

db_file = '../database/database.db'

querier = qdb.queryDatabase(db_file)

city_query = 'SELECT * from city_points;'

cities_sql_out = querier.execute_query(city_query)

ip_asn_dns_query = 'SELECT * from ip_asn_dns'

ip_asn_dns_sql_out = querier.execute_query(ip_asn_dns_query)

ip_to_city_dict = {item[0]: f'{item[3]}, {item[5]}' for item in ip_asn_dns_sql_out}

category_map_v4_path = Path(Path.cwd() / str(result_path('mapping_outputs/categories_map_sol_validated_updated_v4')))

with open(category_map_v4_path, 'rb') as fp:
	category_map_v4 = pickle.load(fp)

caida_geolocation_path = Path(Path.cwd() / str(output_path('location_data/caida_location_output_default')))

with open(caida_geolocation_path, 'rb') as fp:
	caida_geolocation = pickle.load(fp)

caida_geolocation = {k: (float(v[3]), float(v[4])) for k,v in caida_geolocation.items() if v[-1] != 'maxmind'}

voronoi_dir = Path("../helper_data/cities_Voronoi")

standardizer = Standardize_Locations.LocationStandardizer(voronoi_dir)

city_clusters = {}

for count, (k,v) in enumerate(caida_geolocation.items()):
	city_clusters[k] = standardizer.standardize(v)
	if count % 500 == 0:
		print (f'Currently processed {count} entries')

cable_landing_points_sql_out = querier.execute_query('SELECT * from cable_landing_points')

landing_points_sql_out = querier.execute_query('SELECT * from landing_points;')

landing_points_to_standard_city = {f'{item[0]}, {item[2]}': f'{item[5]}, {item[7]}' for item in landing_points_sql_out}

standard_city_to_cable_list = {}

for item in cable_landing_points_sql_out:
	standard_city_name = landing_points_to_standard_city[f'{item[1]},  {item[3]}']
	current_list = standard_city_to_cable_list.get(standard_city_name, [])
	current_list.append(item[0])
	standard_city_to_cable_list[standard_city_name] = current_list


link_to_cable_match = {}
missed_no_match = 0
missed_no_geolocation = 0

for category in category_map_v4:
	for ip_1, ip_2 in category_map_v4[category]:
		city_1 = city_clusters.get(ip_1, '')
		city_2 = city_clusters.get(ip_2, '')
		if city_1 != '' and city_2 != '':
			city_1 = '{}, {}'.format(city_1['CITY'], city_1['COUNTRY'])
			city_2 = '{}, {}'.format(city_2['CITY'], city_2['COUNTRY'])
			cables_1 = standard_city_to_cable_list.get(city_1, [])
			cables_2 = standard_city_to_cable_list.get(city_2, [])
			matched_cables = list(set(cables_1) & set(cables_2))
			if len(matched_cables) > 0:
				link_to_cable_match[(ip_1, ip_2)] = matched_cables
			else:
				missed_no_match += 1
		else:
			missed_no_geolocation += 1

print (f'We missed {missed_no_geolocation} links due to no geolocation and {missed_no_match} for no cable overlap')
print (f'Overall, we have results for {len(link_to_cable_match)}')

print ('Loading our mapping')

our_mapping_path = Path(Path.cwd() / str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v4')))

with open(our_mapping_path, 'rb') as fp:
	our_mapping = pickle.load(fp)

overlap = list(set(our_mapping) & set(link_to_cable_match))

len_mappings = [len(link_to_cable_match[v]) for v in overlap]

print (f'Total cables for iGDB: {sum(len_mappings)} and counter results : {Counter(len_mappings)}')

len_our_mappings = [len(our_mapping[k][1]) for k in overlap]

print (f'Total cables for our mapping: {sum(len_our_mappings)} and counter results : {Counter(len_our_mappings)}')