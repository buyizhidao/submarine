import os, sys
from pathlib import Path
sys.path.insert(1, str(Path(__file__).resolve().parents[2]))
from utils.project_paths import log_path, output_path, raw_path, result_path

import pickle
from collections import namedtuple

TraceRoute = namedtuple('TraceRoute', ['hops', 'other_info'])
Hops = namedtuple('Hops', ['hop', 'ip_address', 'rtt'])

with open('experiments/scn_crit/traceroutes_info_dict', 'rb') as fp:
    traceroutes_info_dict = pickle.load(fp)

print (f'From our experiments, we got {len(traceroutes_info_dict)} traceroutes')

with open(str(result_path('mapping_outputs/link_to_cable_and_score_mapping_sol_validated_v4')), 'rb') as fp:
    mapping_outputs = pickle.load(fp)
    
print (f'From our generated mapping, we have results for {len(mapping_outputs)} links')

all_consecutive_hops_dict = {}

for count, (con_code, traceroute) in enumerate(traceroutes_info_dict.items()):
    construct_tuples = []
    prev_item = traceroute.hops[0]
    for hop in traceroute.hops:
        curr_item = hop
        try:
            if int(curr_item.hop) == int(prev_item.hop) + 1:
                if prev_item.ip_address != '*' and curr_item.ip_address != '*':
                    get_prev_value = all_consecutive_hops_dict.get((prev_item.ip_address, curr_item.ip_address), [])
                    get_prev_value.append(con_code)
                    all_consecutive_hops_dict[(prev_item.ip_address, curr_item.ip_address)] = get_prev_value
                    
        except:
            pass
        prev_item = curr_item
        
print (f' We have {len(all_consecutive_hops_dict)} consecutive hops from our 50 websites experiment')

overlapped_hops = list(set(all_consecutive_hops_dict.keys()) & set(mapping_outputs.keys()))

print (f'Length of overlapped hops with out mapping and our reproduced experiment is {len(overlapped_hops)}')

result_websites_covered = []

for item in overlapped_hops:
    result_websites_covered.extend(all_consecutive_hops_dict[item])
    
print(f'We got traceroutes to run for the following websites : {len(sorted(list(set(result_websites_covered))))}')

import json

with open('experiments/scn_crit/country_ip_sol_bundles.json') as fp:
    country_bundles = json.load(fp)
    
print (f'We ran these experiments for {len(country_bundles)} countries')

all_hops_original = set()

for count, (k, v) in enumerate(country_bundles.items()):
    for dst_ip, contents in v.items():
        for bundle in contents[0]['bundle']:
            all_hops_original.add((bundle['start']['ip'], bundle['end']['ip']))

print (f'From the original experiment, we got results for {len(all_hops_original)} links')

overlap_with_original = list(set(mapping_outputs.keys()) & set(all_hops_original))

print (f'We have an overlap of {len(overlap_with_original)} links, which is around {len(overlap_with_original) / len(all_hops_original) * 100} %')

with open('experiments/scn_crit/country_ip_sol_bundles.json.1') as fp:
    country_bundles = json.load(fp)
    
print (f'We ran these experiments for {len(country_bundles)} countries')

all_hops_original_map = {}

for count, (k, v) in enumerate(country_bundles.items()):
    for dst_ip, contents in v.items():
        for bundle in contents[0]['bundle']:
            all_hops_original_map[(bundle['start']['ip'], bundle['end']['ip'])] = bundle['cables']

print (f'From the original experiment, we got results for {len(all_hops_original_map)} links')

overlap_with_original = list(set(mapping_outputs.keys()) & set(all_hops_original_map))

print (f'We have an overlap of {len(overlap_with_original)} links, which is around {len(overlap_with_original) / len(all_hops_original) * 100} %')

original_pred_count = 0
our_pred_count = 0

for count, item in enumerate(list(overlap_with_original)):
	original_pred_count += len(all_hops_original_map[item])
	our_pred_count += len(mapping_outputs[item][1])

print (f'SCN-Crit mapping count: {original_pred_count} and Nautilus mapping count: {our_pred_count}')
