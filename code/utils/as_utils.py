import pickle, json, sys, copy
from pathlib import Path
from collections import Counter

import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

import reverse_geocode, string, pycountry, pycountry_convert
from unidecode import unidecode
# from nltk.corpus import stopwords

#from validation.identifying_links_to_single_org import generate_as_to_org_map_from_caida
from utils.traceroute_utils import load_all_links_and_ips_data
from utils.merge_data import save_results_to_file
from utils.pickle_compat import load_pickle

from collections import namedtuple
Cable = namedtuple('Cable', ['name', 'landing_points', 'length', 'owners', 'notes', 'rfs', 'other_info'])
from submarine.telegeography_submarine import LandingPoints

# stopwords = stopwords.words('english')

stopwords = ['i', 'me', 'my', 'myself', 'we', 'our', 'ours', 'ourselves', 'you', "you're", "you've", "you'll", "you'd", 'your', 'yours', 'yourself', 'yourselves', 'he', 'him', 'his', 'himself', 'she', "she's", 'her', 'hers', 'herself', 'it', "it's", 'its', 'itself', 'they', 'them', 'their', 'theirs', 'themselves', 'what', 'which', 'who', 'whom', 'this', 'that', "that'll", 'these', 'those', 'am', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing', 'a', 'an', 'the', 'and', 'but', 'if', 'or', 'because', 'as', 'until', 'while', 'of', 'at', 'by', 'for', 'with', 'about', 'against', 'between', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'to', 'from', 'up', 'down', 'in', 'out', 'on', 'off', 'over', 'under', 'again', 'further', 'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'any', 'both', 'each', 'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too', 'very', 's', 't', 'can', 'will', 'just', 'don', "don't", 'should', "should've", 'now', 'd', 'll', 'm', 'o', 're', 've', 'y', 'ain', 'aren', "aren't", 'couldn', "couldn't", 'didn', "didn't", 'doesn', "doesn't", 'hadn', "hadn't", 'hasn', "hasn't", 'haven', "haven't", 'isn', "isn't", 'ma', 'mightn', "mightn't", 'mustn', "mustn't", 'needn', "needn't", 'shan', "shan't", 'shouldn', "shouldn't", 'wasn', "wasn't", 'weren', "weren't", 'won', "won't", 'wouldn', "wouldn't"]

def load_all_ip_to_asn_sources(ip_version=4, tags='default'):

 # Loading data from all ip to asn sources

	directory = str(output_path('ip2as_data/'))

	try:

		with open('{}/rpki_whois_output_v{}_{}'.format(directory, ip_version, tags), 'rb') as fp:
			rpki_asn_dict = pickle.load(fp)

		print (f'From RPKI, we got result for {len(rpki_asn_dict)} IPs')

  
		if ip_version == 4:
			with open('{}/caida_whois_output_v{}_{}'.format(directory, ip_version, tags), 'rb') as fp:
				caida_asn_dict = pickle.load(fp)
		else:
			caida_asn_dict = {}

		print (f'From CAIDA, we got results for {len(caida_asn_dict)} IPs')

		with open('{}/radb_whois_output_v{}_{}'.format(directory, ip_version, tags), 'rb') as fp:
			radb_asn_dict = pickle.load(fp)

		print (f'From RADB, we got results for {len(radb_asn_dict)} IPs')

		with open('{}/cymru_whois_output_v{}_{}'.format(directory, ip_version, tags), 'rb') as fp:
			cymru_asn_dict = pickle.load(fp)

		print (f'From Cymru, we got results for {len(cymru_asn_dict)} IPs')

		return (rpki_asn_dict, caida_asn_dict, radb_asn_dict, cymru_asn_dict)

	except Exception as e:

		print (f'Most likely the required files were not generated. We got the error: {str(e)}')
		sys.exit(1)



def load_submarine_and_asn_data():

	save_file = raw_path('submarine_data/owners_dict')

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			submarine_owners = load_pickle(fp)
	else:
		print (f'Run submarine module before running this')
		sys.exit(1)

	save_file = raw_path('submarine_data/cable_info_dict')

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			cable_dict = load_pickle(fp)
	else:
		print (f'Run submarine module before running this')
		sys.exit(1)

	save_file = raw_path('submarine_data/landing_points_dict')

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			landing_points_dict = load_pickle(fp)
	else:
		print (f'Run submarine module before running this')
		sys.exit(1)

	save_file = output_path('asns.jsonl')

	asn_data = []

	if Path(save_file).exists():
		with open(save_file) as fp:
			content = fp.readlines()
		for line in content:
			asn_data.append(json.loads(line))
	else:
		print ('Run asrank script before running this')
		sys.exit(1)

	save_file = output_path('asnLinks.jsonl')

	asnlinks_data = []

	if Path(save_file).exists():
		with open(save_file) as fp:
			content = fp.readlines()
		for line in content:
			asnlinks_data.append(json.loads(line))
	else:
		print ('Run asrank script before running this')
		sys.exit(1)

	return submarine_owners, cable_dict, landing_points_dict, asn_data, asnlinks_data



def get_ip_to_asn_for_all_ips (all_ips, ip_version=4):

	ip_to_asn_dict = {}
	missed = 0
	individual_missed = [0, 0, 0, 0]

	rpki_asn_dict, caida_asn_dict, radb_asn_dict, cymru_asn_dict = load_all_ip_to_asn_sources(ip_version=ip_version)

	for count, ip in enumerate(all_ips):
		result = []
		rpki_res = rpki_asn_dict.get(ip, None)
		if rpki_res:
			result.extend([item.replace('AS', '') for item in rpki_res])
		else:
			individual_missed[0] += 1

		cymru_res = cymru_asn_dict.get(ip, None)
		if cymru_res:
			result.append(str(cymru_res[1]))
		else:
			individual_missed[1] += 1

		radb_res = radb_asn_dict.get(ip, None)
		if radb_res:
			result.extend([item.replace('AS', '') for item in radb_res])
		else:
			individual_missed[2] += 1

		caida_res = caida_asn_dict.get(ip, None)
		if caida_res:
			result.extend(caida_res)
		else:
			individual_missed[3] += 1

  # print (f'RPKI: {rpki_res}, Cymru: {cymru_res}, RADB: {radb_res}, caida: {caida_res}')

		asn_res = Counter(result).most_common()

		if len(asn_res) > 0:
			asn_res = asn_res[0][0]

		if len(asn_res) == 0:
			missed += 1
		else:
			ip_to_asn_dict[ip] = asn_res

	print (f'IP to ASN mapping generated for {len(ip_to_asn_dict)} IPs and missed for {missed} IPs')
	print (f'Individual misses are {individual_missed}')

	counter = Counter(ip_to_asn_dict.values())
	print (f'Top 10 ASN are : {counter.most_common(10)}')

	return ip_to_asn_dict



def get_country_for_each_operator(submarine_owners, cable_dict, landing_points_dict):

	org_to_country_map = {}

	for count, (org, cables) in enumerate(submarine_owners.items()):
		result = []
		for cable in cables:
			var = set()
			for landing_point in cable_dict[cable].landing_points:
				landing_point_coordinates = (landing_points_dict[landing_point].latitude, landing_points_dict[landing_point].longitude)
				country = reverse_geocode.search([landing_point_coordinates])[0]['country_code']
				#country = landing_points_dict[landing_point].country
				var.add(country)
			result.extend(list(var))

  # Some orgs in CAIDA have country as EU, so let's take care of that scenario as well
		for res in result:
			try:
				if pycountry_convert.country_alpha2_to_continent_code(res) == 'EU':
					result.append('EU')
			except:
				continue

  # Check if any country name already present in the org name
		for country in pycountry.countries:
			if country.name.lower() in org.lower() or country.alpha_2.lower() in org.lower().split():
				print (f'Added {country.alpha_2} for org : {org}')
				result.append(country.alpha_2)

		org_to_country_map[org] = result

	return org_to_country_map



def strip_punctuations_and_accents (org, stopwords=stopwords):

 # Removing punctuations
	org = org.translate(str.maketrans(' ', ' ', string.punctuation)).lower()
	org = ' '.join([item for item in org.split() if item.lower() not in stopwords])
	return unidecode(org)



def compute_short_form_for_org (org):

	try:
  
	 # If length is 1, we will return it as is
		if len(org.strip().split()) == 1:
			return org
		else:
		 # Sometimes, the orgs first word is all caps, which might indicate the short form
			org_first_word = org.split()[0]
			if org_first_word.isupper():
				return org_first_word

			else:
			 # If , or ( in org, we will assume first part as the key org name
				if ',' in org:
					org = org.split(',')[0]
				if '(' in org:
					org = org.split('(')[0]

    # It is likely the capital letters will form the shor form for the org
				cap_letters = ''.join([item for item in org if item.isupper() or item.isnumeric()])
				if len(cap_letters) > 5:
					cap_letters = cap_letters[:5]
				return cap_letters
	except:
		return None



def compute_short_forms_for_orgs_list (orgs_list):

	org_to_short_form = {}
	short_form_to_org = {}

	for org in orgs_list:
		short_form = compute_short_form_for_org(org)
		if short_form:
			org_to_short_form[org] = short_form
			current_orgs = short_form_to_org.get(short_form, [])
			current_orgs.append(org)
			short_form_to_org[short_form] = current_orgs

	return org_to_short_form, short_form_to_org



def clean_given_org_list (orgs_list, stopwords=stopwords, most_common=None):

	org_to_clean_org = {}
	clean_org_to_org = {}

	if most_common:
		stopwords += most_common

	for org in orgs_list:
		clean_org = strip_punctuations_and_accents(org, stopwords)
		org_to_clean_org[org] = clean_org
		clean_org_to_org[clean_org] = org 

	return org_to_clean_org, clean_org_to_org



def generate_as_mapping_based_on_caida_asrank_data (asn_data):

	org_to_rank_dict = {}
	org_to_asn_dict = {}
	org_to_country_map = {}
	asn_name_to_rank_dict = {}
	asn_name_to_org_dict = {}

	errors = 0

	for item in asn_data:
		try:
			asn = item['asn']
			rank = item['rank']
			org_name = item['organization']['orgName']
			asn_name = item['asnName']
			country = item['country']['iso']

			# Only ASN are likely to be unique
			# Let's first fill org_to_rank_dict
			current_ranks = org_to_rank_dict.get(org_name, [])
			current_ranks.append(rank)
			org_to_rank_dict[org_name] = current_ranks

			# Next we will fill the org to asn dict
			current_asns = org_to_asn_dict.get(org_name, [])
			current_asns.append(asn)
			org_to_asn_dict[org_name] = current_asns

			# Next we fill the org to country
			# It is likely that some ASN of an org could be in a different country
			current_countries = org_to_country_map.get(org_name, [])
			current_countries.append(country)
			org_to_country_map[org_name] = current_countries

			# Next we fill the asn_name_to_rank_dict
			current_ranks = asn_name_to_rank_dict.get(asn_name, [])
			current_ranks.append(rank)
			asn_name_to_rank_dict[asn_name] = current_ranks

			# Finally we fill the asn_name_to_org_dict
			current_orgs = asn_name_to_org_dict.get(asn_name, [])
			current_orgs.append(org_name)
			asn_name_to_org_dict[asn_name] = current_orgs

		except:
			errors += 1
			continue

	print (f'Error count was : {errors}')

	return org_to_rank_dict, org_to_asn_dict, org_to_country_map, asn_name_to_rank_dict, asn_name_to_org_dict



def compute_most_common_words_in_given_org_list (orgs_list):

	all_orgs = ' '.join(orgs_list).split()
	counter = Counter(all_orgs)
	most_common_words = [item[0] for item in counter.most_common(100)]
 
	# If country names in the list, we will try to remove them
	most_common_words_copy = copy.deepcopy(most_common_words)
	for word in most_common_words_copy:
		try:
			pycountry.countries.lookup(word)
			print (f'Removing the word {word}')
			most_common_words.remove(word)
		except:
			continue

	return most_common_words



def check_name_overlap (submarine_org, caida_org_list):

	if len(submarine_org.split()) == 1:
		match = [item for item in caida_org_list if submarine_org.lower() in [i.lower().strip(',') for i in item.split()]]
	else:
		match = [item for item in caida_org_list if submarine_org.lower() in item.lower()]

	return match



def check_asn_name_overlap (submarine_org, caida_asn_name_list):

	match = [item for item in caida_asn_name_list if submarine_org.lower() in [i.lower() for i in item.split('-')]]
	return match



def check_short_form_overlap (submarine_org, caida_short_form_list):

	match = [item for item in caida_short_form_list if item.lower().startswith(submarine_org.lower())]
	return match



def examine_matched_orgs_validity (matched_orgs, submarine_owner_countries, caida_org_to_country_map):

	for org in matched_orgs:
		if len(set(submarine_owner_countries) & set(caida_org_to_country_map[org])) == 0:
		 # print (f'Org {org} not satisifed country constraints')
			matched_orgs.remove(org)



def extract_customers_for_all_asn (asnlinks_data):

	asn_to_customer_asn_map = {}
	errors = 0

	for value in asnlinks_data:
		try:
			if value['relationship'] == 'provider':
				provider = value['asn1']['asn']
				customer = value['asn0']['asn']
			elif value['relationship'] == 'customer':
				provider = value['asn0']['asn']
				customer = value['asn1']['asn']

			current_customers = asn_to_customer_asn_map.get(provider, [])
			current_customers.append(customer)
			asn_to_customer_asn_map[provider] = current_customers
		except:
			errors += 1
			continue

	print (f"Errors: {errors}, example 3356 customers: {len(asn_to_customer_asn_map['3356'])}")

	return asn_to_customer_asn_map



def generate_asn_list_given_best_org_match (best_match_org, all_matches, asn_to_customer_asn_map, caida_org_to_asn_dict):

	asn_list = caida_org_to_asn_dict[best_match_org]
	for org in all_matches:
		org_asn = caida_org_to_asn_dict[org]
		current_asn_list_customers = []
  
		for asn in asn_list:
			try:
				current_asn_list_customers.extend(asn_to_customer_asn_map[asn])
			except:
				continue

  # Ideally we are checking if the earlier matches are providers for the current ones
		if len(set(current_asn_list_customers) & set(org_asn)) > 0:
			asn_list.extend(org_asn)
 
	return list(set(asn_list))



def get_best_fit_caida_org_name_for_submarine_owner():

	submarine_owners, cable_dict, landing_points_dict, asn_data, asnlinks_data = load_submarine_and_asn_data()
	submarine_org_to_country_map = get_country_for_each_operator(submarine_owners, cable_dict, landing_points_dict)

	# Loading the required details from CAIDA ASRank
	caida_org_to_rank_dict, caida_org_to_asn_dict, caida_org_to_country_map, caida_asn_name_to_rank_dict, caida_asn_name_to_org_dict = generate_as_mapping_based_on_caida_asrank_data (asn_data)

	# Computing the short forms for all CAIDA orgs before hand, rather than repeated computation
	caida_org_to_short_form, caida_short_form_to_org = compute_short_forms_for_orgs_list(list(caida_org_to_rank_dict.keys()))

	# Generating the cleaned org names for all CAIDA orgs
	caida_org_to_clean_org, caida_clean_org_to_org = clean_given_org_list(list(caida_org_to_asn_dict.keys()), stopwords=stopwords, most_common=None)

	# 100 most common words in CAIDA org names
	caida_common_words = compute_most_common_words_in_given_org_list(list(caida_clean_org_to_org.keys()))

	# Let's rank each submarine owner based on the number of cables they have
	submarine_owners_ranked = {k:v for k,v in sorted(submarine_owners.items(), key=lambda x: len(x[1]), reverse=True)}

	# ASN to customer ASN map
	asn_to_customer_asn_map = extract_customers_for_all_asn(asnlinks_data)

	submarine_owner_to_asn_list = {}

	print ('*' * 50)

	for count, org in enumerate(submarine_owners_ranked.keys()):

		original_org = org
		#print (f'Currently checking for submarine owner: {org}')
		cleaned_org = strip_punctuations_and_accents(org, stopwords=stopwords)
		#print (f'Cleaned org name is {cleaned_org}')

		check = False

		if '(' in org:
			org_parts = [strip_punctuations_and_accents(item.strip(')').strip(), stopwords=stopwords) for item in org.split('(')]
			check = True


		all_matches = set()
		all_matches_failure = set()

		# Matching with name overlap
		if check:
			for cleaned_org in org_parts:
				match = check_name_overlap(cleaned_org, list(caida_clean_org_to_org.keys()))
				if len(match) > 0:
					match = [caida_clean_org_to_org[item] for item in match]
					all_matches_failure.update(match)
					examine_matched_orgs_validity(match, submarine_org_to_country_map[org], caida_org_to_country_map)
					all_matches.update(match)
		else:
			match = check_name_overlap(cleaned_org, list(caida_clean_org_to_org.keys()))
			if len(match) > 0:
				match = [caida_clean_org_to_org[item] for item in match]
				all_matches_failure.update(match)
				examine_matched_orgs_validity(match, submarine_org_to_country_map[org], caida_org_to_country_map)
				all_matches.update(match)

  # Matching with asn name overlap
		if check:
			for cleaned_org in org_parts:
				match = check_asn_name_overlap(cleaned_org, list(caida_asn_name_to_rank_dict.keys()))
				if len(match) > 0:
				 # Let's match to the best one
					match = [caida_asn_name_to_org_dict[item][0] for item in match]
					all_matches_failure.update(match)
					examine_matched_orgs_validity(match, submarine_org_to_country_map[org], caida_org_to_country_map)
					all_matches.update(match)
		else:
			match = check_asn_name_overlap(cleaned_org, list(caida_asn_name_to_rank_dict.keys()))
			if len(match) > 0:
			 # Let's match to the best one
				match = [caida_asn_name_to_org_dict[item][0] for item in match]
				all_matches_failure.update(match)
				examine_matched_orgs_validity(match, submarine_org_to_country_map[org], caida_org_to_country_map)
				all_matches.update(match)

  # Matching with short form
		if check:
			for cleaned_org in org_parts:
				match = check_short_form_overlap(cleaned_org, list(caida_short_form_to_org.keys()))
				if len(match) > 0:
				 # Let's match the best one
					match = [caida_short_form_to_org[item][0] for item in match]
					all_matches_failure.update(match)
					examine_matched_orgs_validity(match, submarine_org_to_country_map[org], caida_org_to_country_map)
					all_matches.update(match)
		else:
			match = check_short_form_overlap(cleaned_org, list(caida_short_form_to_org.keys()))
			if len(match) > 0:
			 # Let's match the best one
				match = [caida_short_form_to_org[item][0] for item in match]
				all_matches_failure.update(match)
				examine_matched_orgs_validity(match, submarine_org_to_country_map[org], caida_org_to_country_map)
				all_matches.update(match)

  
		if len(all_matches) > 0:
			match_rank = {org: caida_org_to_rank_dict[org][0] for org in list(all_matches)}
			best_match = min(match_rank.items(), key=lambda x: x[1])
			#print (f'We got best match with {best_match}')

			# Sorting to ensure that Orgs with lower AS rank (ie., starting with rank 1 and then going downwards) are placed first
			match_rank_sorted = {k:v for k,v in sorted(match_rank.items(), key=lambda x:x[1])}

			if best_match[1] < 5000:
			 #print ('Generating at position 1')
				asn_list = generate_asn_list_given_best_org_match (best_match[0], list(match_rank_sorted.keys()), asn_to_customer_asn_map, caida_org_to_asn_dict)
				submarine_owner_to_asn_list[original_org] = asn_list
			else:
			 #print ('Generating at position 1.1')
				submarine_owner_to_asn_list[original_org] = caida_org_to_asn_dict[best_match[0]]
    

		if len(all_matches) == 0 or best_match[1] >= 5000:
		 # Looks like we didn't get good matches. Let's eliminate some common words and check
			stopwords_updated = stopwords + caida_common_words
			cleaned_org_new = strip_punctuations_and_accents(org, stopwords=stopwords_updated)
			#print (f'Cleaned org now is : {cleaned_org_new}')

			if cleaned_org_new == cleaned_org and len(cleaned_org_new.split()) == 1:
			 #print (f'There is not much we can do, leave it as is')

				if len(all_matches) > 0:
					match_rank = {org: caida_org_to_rank_dict[org][0] for org in list(all_matches)}
					best_match = min(match_rank.items(), key=lambda x: x[1])
					#print (f'We got best match with {best_match}')

					#print ('Generating at position 2')
					# Sorting to ensure that Orgs with lower AS rank (ie., starting with rank 1 and then going downwards) are placed first
					match_rank_sorted = {k:v for k,v in sorted(match_rank.items(), key=lambda x:x[1])}
					asn_list = generate_asn_list_given_best_org_match (best_match[0], list(match_rank_sorted.keys()), asn_to_customer_asn_map, caida_org_to_asn_dict)
					submarine_owner_to_asn_list[original_org] = asn_list

				else:
					if len(all_matches_failure) > 0:
					 #print ('Generating at position 3')
						match_rank = {org: caida_org_to_rank_dict[org][0] for org in list(all_matches_failure)}
						best_match = min(match_rank.items(), key=lambda x: x[1])
						#print (f'Best match alternative {best_match}')
           
						# For negative cases, let's just add the best rank one
						submarine_owner_to_asn_list[original_org] = caida_org_to_asn_dict[best_match[0]]
   
			else:
    
				org_parts = cleaned_org_new.split()

				# We will only do name match
				for cleaned_org in org_parts:
					match = check_name_overlap(cleaned_org, list(caida_clean_org_to_org.keys()))
					if len(match) > 0:
						match = [caida_clean_org_to_org[item] for item in match]
						all_matches_failure.update(match)
						examine_matched_orgs_validity(match, submarine_org_to_country_map[org], caida_org_to_country_map)
						all_matches.update(match)

				if len(all_matches) > 0:
					match_rank = {org: caida_org_to_rank_dict[org][0] for org in list(all_matches)}
					best_match = min(match_rank.items(), key=lambda x: x[1])
					#print (f'Final best match with {best_match}')

					#print ('Generating at position 4')
					# Sorting to ensure that Orgs with lower AS rank (ie., starting with rank 1 and then going downwards) are placed first
					match_rank_sorted = {k:v for k,v in sorted(match_rank.items(), key=lambda x:x[1])}
					asn_list = generate_asn_list_given_best_org_match (best_match[0], list(match_rank_sorted.keys()), asn_to_customer_asn_map, caida_org_to_asn_dict)
					current_asn_list = submarine_owner_to_asn_list.get(original_org, [])
					current_asn_list.extend(asn_list)
					submarine_owner_to_asn_list[original_org] = current_asn_list
    
				if len(all_matches_failure) > 0:
					match_rank = {org: caida_org_to_rank_dict[org][0] for org in list(all_matches_failure)}
					best_match = min(match_rank.items(), key=lambda x: x[1])
					#print (f'Best match alternative {best_match}')

					#print('Generating at position 5')
					current_asn_list = submarine_owner_to_asn_list.get(original_org, [])
					current_asn_list.extend(caida_org_to_asn_dict[best_match[0]])
					submarine_owner_to_asn_list[original_org] = current_asn_list


  #print ('*' * 50)

  
		if count % 100 == 0:
			print (f'Finished processing {count} of {len(submarine_owners_ranked)}')


	print (f'Example length of Orange : {len(submarine_owner_to_asn_list["Orange"])}')

	# Let's save the results for future use
	save_directory = output_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	save_file = 'submarine_owner_to_asn_list'

	print ('Saving the submarine owner to asn list result')
	save_results_to_file(submarine_owner_to_asn_list, str(save_directory), save_file)

	return submarine_owner_to_asn_list



def generate_closest_submarine_org (all_ips, ip_version=4):

	save_directory = output_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	ip_to_closest_submarine_org_file = 'ip_to_closest_submarine_org_v{}'.format(ip_version)
	submarine_owner_to_asn_list_file = 'submarine_owner_to_asn_list'

	if Path(save_directory / ip_to_closest_submarine_org_file).exists():
		print ('Directly loading IP to submarine org mapping')
		with open(save_directory / ip_to_closest_submarine_org_file, 'rb') as fp:
			ip_to_closest_submarine_org = pickle.load(fp)

	else:
		ip_to_closest_submarine_org = {}

		print ('Lets check if we have submarine owner to asn list')
		if Path(save_directory / submarine_owner_to_asn_list_file).exists():
			print ('Directly loading submarine_owner_to_asn_list')
			with open(save_directory / submarine_owner_to_asn_list_file, 'rb') as fp:
				submarine_owner_to_asn_list = pickle.load(fp)
		else:
			submarine_owner_to_asn_list = get_best_fit_caida_org_name_for_submarine_owner()

  # Constructing a reverse dict for easier lookup
		asn_to_submarine_owner_map = {}
		for submarine_owner, asn_list in submarine_owner_to_asn_list.items():
			for asn in asn_list:
				current_owners = asn_to_submarine_owner_map.get(asn, [])
				current_owners.append(submarine_owner)
				asn_to_submarine_owner_map[asn] = current_owners

		ip_to_asn_dict = get_ip_to_asn_for_all_ips (all_ips, ip_version=ip_version)

		for ip, asn in ip_to_asn_dict.items():
			owner = asn_to_submarine_owner_map.get(asn, None)
			if owner:
				current_owners = ip_to_closest_submarine_org.get(ip, [])
				current_owners.extend(owner)
				ip_to_closest_submarine_org[ip] = list(set(current_owners)) 

  # Saving results for next time lookup
		print ('Saving results to file')
		save_results_to_file(ip_to_closest_submarine_org, str(save_directory), ip_to_closest_submarine_org_file)

	print (f'We got a match for {len(ip_to_closest_submarine_org)} IPs of {len(all_ips)} IPs')

	return ip_to_closest_submarine_org



if __name__ == '__main__':

	links, all_ips = load_all_links_and_ips_data (ip_version=4)

	generate_closest_submarine_org (all_ips, ip_version=4)
