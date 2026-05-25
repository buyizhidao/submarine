import re, json, pickle, sys
from collections import Counter
from pathlib import Path
from utils.project_paths import log_path, output_path, raw_path, result_path

# AS2Org data & script taken from CAIDA (https://catalog.caida.org/details/recipe/getting_an_asns_name_country_organization)

def generate_as_to_org_map_from_caida():

	re_format= re.compile("# format:(.+)")

	org_info = {}
	asn_info = {}

	if not Path(str(output_path('as2org_info.txt'))).is_file():
		print ('Download data relevant AS2Org info txt file from "https://publicdata.caida.org/datasets/as-organizations/" and save the unzipped file in data/intermediate directory')
		sys.exit(1)

	with open(str(output_path('as2org_info.txt'))) as fp:
		for line in fp:
			m = re_format.search(line)
			if m:
				keys = m.group(1).rstrip().split(',')
				keys = keys[0].split('|')
				if keys[0] == 'aut':
				    # Replace all instances of 'aut' with 'asn'
				    keys[0] = 'asn'
				    # Replace all instances of 'aut_name' with 'asn_name'
				    keys[2] = 'asn_name'

      
   # skips over comments
			if len(line) == 0 or line[0] == "#":
			    continue

			values = line.rstrip().split("|")

			info = {}

			for i,key in enumerate(keys):
			    info[keys[i]] = values[i]
      

			if "asn" == keys[0]:
				org_id = info["org_id"]
				if org_id in org_info:
				    for key in ["org_name","country"]:
				        info[key] = org_info[org_id][key]
     
				asn_info[values[0]] = info

			elif "org_id" == keys[0]:
			    org_info[values[0]] = info
			else:
			    print ("unknown type",keys[0],file= sys.stderr)


	asn_to_org_name_map = {}
	org_name_to_asn_map = {}

	for asn, values in asn_info.items():
	    asn_to_org_name_map[asn] = values['org_name']
	    asn_list = org_name_to_asn_map.get(values['org_name'], [])
	    asn_list.append(asn)
	    org_name_to_asn_map[values['org_name']] = asn_list

	return (asn_to_org_name_map, org_name_to_asn_map)


def compute_asn_for_all_links_from_all_sources():

	result_dir = str(output_path(''))

	# First let's load all the IPs 
	with open(result_dir + 'mapping_outputs/all_ips_v4', 'rb') as fp:
		all_ips = pickle.load(fp)

 # Load data from individual sources
	with open(result_dir + 'ip2as_data/caida_whois_output_v4_default', 'rb') as fp:
		caida_ip_to_asn_map = pickle.load(fp)

	with open(result_dir + 'ip2as_data/cymru_whois_output_v4_default', 'rb') as fp:
		cymru_whois_ip_to_asn_map = pickle.load(fp)

	with open(result_dir + 'ip2as_data/radb_whois_output_v4_default', 'rb') as fp:
		whois_radb_ip_to_asn_map = pickle.load(fp)

	with open(result_dir + 'ip2as_data/rpki_whois_output_v4_default', 'rb') as fp:
		whois_rpki_ip_to_asn_map = pickle.load(fp)

 # Now let's loop over all IPs and collect the results
	ip_to_asn_aggregated = {}
	missed_count = 0

	for count, ip in enumerate(all_ips):
	    whois_rpki_res = whois_rpki_ip_to_asn_map.get(ip, [])
	    if whois_rpki_res != []:
	        whois_rpki_res = [item.replace('AS', '') for item in whois_rpki_res]
     
	    cymru_res = cymru_whois_ip_to_asn_map.get(ip, [])
	    if cymru_res != []:
	        cymru_res = [str(cymru_res)]
     
	    whois_radb_res = whois_radb_ip_to_asn_map.get(ip, [])
	    if whois_radb_res != []:
	        whois_radb_res = [item.replace('AS', '') for item in whois_radb_res]
     
	    caida_res = caida_ip_to_asn_map.get(ip, [])
     
	    all_res = [whois_rpki_res, cymru_res, caida_res, whois_radb_res]
     
	    all_res_extended = whois_rpki_res.copy()
	    all_res_extended.extend(cymru_res)
	    all_res_extended.extend(caida_res)
	    all_res_extended.extend(whois_radb_res)
     
	    # Let's take the most commonly occuring ASN across the sources
	    asn_res = Counter(all_res_extended).most_common()
     
	    if len(asn_res) > 0:
	        asn_res = asn_res[0][0]
         
	    if len(asn_res) == 0:
	        missed_count += 1
	    else:
	        ip_to_asn_aggregated[ip] = asn_res

	print (f'Got IP to ASN mapping for {len(ip_to_asn_aggregated)} IPs and missed {missed_count} IPs')

	return ip_to_asn_aggregated


def convert_asn_to_standard_org_names(ip_to_asn_aggregated, asn_to_org_name_map):

	ip_to_standard_org_aggregated = {}
	missed_count = 0

	for ip, aggregated_asn in ip_to_asn_aggregated.items():
		try:
			ip_to_standard_org_aggregated[ip] = asn_to_org_name_map[aggregated_asn]
		except:
			missed_count += 1
			pass

	print (f'Got IP to Standard Org results for {len(ip_to_standard_org_aggregated)} IPs and missed {missed_count} IPs')

	return ip_to_standard_org_aggregated


def extract_all_ips_belonging_to_org(ip_to_standard_org_aggregated, org_name):

	matched_ips = []
	matched_orgs = set()

	for ip, standard_org in ip_to_standard_org_aggregated.items():
		if org_name.lower() in standard_org.lower():
			matched_orgs.add(standard_org)
			matched_ips.append(ip)

	print (f'Matched orgs were {matched_orgs}')

	print ('*' * 50)

	return matched_ips


def get_all_links_that_match_particular_org(ip_to_standard_org_aggregated, org_name, mode=0):

	matched_ips = extract_all_ips_belonging_to_org(ip_to_standard_org_aggregated, org_name)
	print (f'For {org_to_match}, we found {len(matched_ips)} IPs')

	with open(str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v4')), 'rb') as fp:
		mapping_outputs = pickle.load(fp)

	print (f'Mapping outputs length is {len(mapping_outputs)}')

	matched_link_subset = []
	matched_cables_with_count = {}

	category_to_cutoff_score = {'bg_oc': 0.85, 'og_oc': 0.78, 'bb_oc': 0.7, 'bg_te': 0.425, 'og_te': 0.39, 'bb_te': 0.35}

	for count, (link, mapping) in enumerate(mapping_outputs.items()):
		org_1 = ip_to_standard_org_aggregated.get(link[0], '')
		org_2 = ip_to_standard_org_aggregated.get(link[1], '')
		if org_name.lower() in org_1.lower() or org_name.lower() in org_2.lower():
			matched_link_subset.append(link)
			if mode == 0:
				if len(mapping[1]) > 0:
					if 'oc' in mapping[-1] and mapping[2][index] >= category_to_cutoff_score[mapping[-1]]:
						current_count = matched_cables_with_count.get(mapping[1][0], [0, [], []])
						current_count[0] += 1
						current_count[1].append(mapping[-1])
						current_count[2].append(round(mapping[2][0], 1))
						# in the order of count, category, score
						matched_cables_with_count[mapping[1][0]] = current_count
			elif mode == 1:
				for index, cable in enumerate(mapping[1]):
					if 'oc' in mapping[-1] and mapping[2][index] >= category_to_cutoff_score[mapping[-1]]:
						current_count = matched_cables_with_count.get(cable, [0, [], []])
						current_count[0] += 1
						current_count[1].append(mapping[-1])
						current_count[2].append(round(mapping[2][index], 1))
						matched_cables_with_count[cable] = current_count

	matched_cables_with_count_sorted = {k:(v[0], Counter(v[1]), Counter(v[2])) for k,v in sorted(matched_cables_with_count.items(), key=lambda x: x[1][0], reverse=True)}

	print (f'Overall matched links are {len(matched_link_subset)}')

	print (json.dumps(matched_cables_with_count_sorted, indent=3))

	print ('*' * 50)
 
	print (matched_cables_with_count_sorted.keys())



if __name__ == '__main__':

	asn_to_org_name_map, org_name_to_asn_map = generate_as_to_org_map_from_caida()

	print (f'From CAIDA AS2Org, we got data for {len(asn_to_org_name_map)} ASNs')

	ip_to_asn_aggregated = compute_asn_for_all_links_from_all_sources()

	ip_to_standard_org_aggregated = convert_asn_to_standard_org_names(ip_to_asn_aggregated, asn_to_org_name_map)

	org_to_match = 'Vodafone'

	get_all_links_that_match_particular_org(ip_to_standard_org_aggregated, org_to_match, 1)

 