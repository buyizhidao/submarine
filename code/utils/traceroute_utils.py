import pickle, random
from pathlib import Path
import subprocess
from copy import deepcopy

import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import get_logger

from utils.merge_data import save_results_to_file

logger = get_logger(__name__)


def merge_ab_and_ba_links (dictionary, codes=None, mode=0):
    merge_count = 0
    for key in list(dictionary):
        if key[::-1] in dictionary.keys():
            val1 = dictionary.get(key)
            val2 = dictionary.get(key[::-1])
            if val1 and val2:
                merge_count += 1
                
                if mode == 1:
                    if codes:
                        merge_val = [val1[0]+val2[0], codes]
                    else:
                        codes = list(set(val1[-1] + val2[-1]))
                        merge_val = [val1[0]+val2[0], codes]
                else:
                    merge_val = [ val1 + val2 ]
                
                if (mode == 1 and len(val1[0]) > len(val2[0])) or\
                 (mode == 0 and len(val1) > len(val2)):
                    dictionary[key] = merge_val
                    dictionary.pop(key[::-1])
                else:
                    dictionary[key[::-1]] = merge_val
                    dictionary.pop(key)
        else:
        	if mode == 1:
        		dictionary[key] = dictionary[key]
        	else:
        		dictionary[key] = [dictionary[key]]
    
    logger.info('Merge count is %d', merge_count)



def add_tags(dictionary, code):
    for key in dictionary:
        dictionary[key].append(code)


def _default_ripe_measurements(ip_version=4):
	if ip_version == 4:
		return [5051, 5151]
	return [6052, 6152]


def _latest_ripe_uniq_file(ripe_directory, msm, ip_version):
	files = [
	 file for file in Path(ripe_directory).glob(f'*{msm}*v{ip_version}*')
	 if 'uniq_ip_dict' in file.name and file.is_file()
	]
	if not files:
		raise FileNotFoundError(
		 f'No RIPE uniq traceroute file found for measurement {msm} and IPv{ip_version} in {ripe_directory}'
		)
	return max(files, key=lambda file: file.stat().st_mtime)


def _merge_processed_traceroute_dict(target, source):
	for link, value in source.items():
		if link in target:
			target[link] = [target[link][0] + value[0], list(set(target[link][-1] + value[-1]))]
		else:
			target[link] = deepcopy(value)


def _save_links_and_ips(traceroute_dict, ip_version=4):
	save_directory = output_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	links = list(traceroute_dict.keys())

	save_results_to_file(traceroute_dict, str(save_directory), 'full_processed_traceroute_output_v{}'.format(ip_version))
	save_results_to_file(links, str(save_directory), 'links_v{}'.format(ip_version))

	uniq_ips = set()
	for ip_1, ip_2 in links:
		uniq_ips.add(ip_1)
		uniq_ips.add(ip_2)

	uniq_ips_list = list(uniq_ips)
	logger.info('# of uniq IPs: %d', len(uniq_ips_list))
	save_results_to_file(uniq_ips_list, str(save_directory), 'all_ips_v{}'.format(ip_version))

	return links, uniq_ips_list


def generate_links_and_ips_from_ripe_only(ip_version=4, measurements=None):
	ripe_directory = output_path('ripe_data/')
	measurements = measurements or _default_ripe_measurements(ip_version)

	traceroute_dict = {}
	for msm in measurements:
		ripe_file = _latest_ripe_uniq_file(ripe_directory, msm, ip_version)
		logger.info('Loading RIPE file: %s', ripe_file)
		with open(ripe_file, 'rb') as fp:
			ripe_dict = pickle.load(fp)

		merge_ab_and_ba_links(ripe_dict)
		add_tags(ripe_dict, ['r-{}'.format(msm)])
		logger.info('RIPE %s dict length is %d', msm, len(ripe_dict))
		_merge_processed_traceroute_dict(traceroute_dict, ripe_dict)

	merge_ab_and_ba_links(traceroute_dict, None, 1)
	logger.info('Finally, we have %d RIPE-only traceroute links', len(traceroute_dict))
	return _save_links_and_ips(traceroute_dict, ip_version)


def generate_links_and_ips_from_all_sources (ip_version=4, manual=False):

 # Let's first load the data from CAIDA
	caida_directory = output_path('caida_data/')
	ripe_directory = output_path('ripe_data/')

	# We will automatically take the last file
	if not manual:

	 # First let's do it for CAIDA
		cmd_str = 'ls -ltr {}/*v{}*'.format(str(caida_directory), ip_version)
		p = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE)
		result = p.communicate()[0].decode()
		caida_file = [item.split()[-1] for item in result.split('\n')[:-1]]

		caida_dict = {}
		count = 0

		for file in caida_file:
			if 'uniq' in file:
				count += 1
				logger.info('Opening CAIDA file: %s', file)
				with open(file, 'rb') as fp:
					individual_caida_dict = pickle.load(fp)

				for link, rtts in individual_caida_dict.items():
					if link in caida_dict:
						caida_dict[link].extend(rtts)
					else:
						caida_dict[link] = rtts

  # Let's save this CAIDA dict for future uses
		if count > 1:
			logger.info('Dumping the output for future use')
			with open(caida_directory/'uniq_ip_dict_caida_all_links_v{}_merged'.format(ip_version), 'wb') as fp:
				pickle.dump(caida_dict, fp)

		merge_ab_and_ba_links(caida_dict)
		add_tags(caida_dict, ['c-v{}'.format(ip_version)])

		logger.info('CAIDA dict length is %d', len(caida_dict))

		if ip_version == 4:
			msm_id = [5051, 5151]
		else:
			msm_id = [6052, 6152]

		ripe_dicts = []

		for msm in msm_id:
			cmd_str = 'ls -ltr {}/*{}*'.format(str(ripe_directory), msm)
			p = subprocess.Popen(cmd_str, shell=True, stdout=subprocess.PIPE)
			result = p.communicate()[0].decode()
			ripe_file = result.split('\n')[-2].split()[-1]

			if 'uniq' in ripe_file:
				logger.info('Loading file: %s', ripe_file)
				with open(ripe_file, 'rb') as fp:
					ripe_dict = pickle.load(fp)

				merge_ab_and_ba_links(ripe_dict)

				add_tags(ripe_dict, ['r-{}'.format(msm)])

				logger.info('RIPE %s dict length is %d', msm, len(ripe_dict))

				ripe_dicts.append(ripe_dict)


		traceroute_dict = caida_dict.copy()
		for ripe_dict in ripe_dicts:
			traceroute_dict.update(ripe_dict)

		common_keys_r_r = list(set(ripe_dicts[0].keys()) & set(ripe_dicts[1].keys()))
		common_keys_r0_c = list(set(ripe_dicts[0].keys()) & set(caida_dict.keys()))
		common_keys_r1_c = list(set(ripe_dicts[1].keys()) & set(caida_dict.keys()))
		all_common_keys = list(set(ripe_dicts[0].keys()) & set(ripe_dicts[1].keys()) & set(caida_dict.keys()))

		for item in common_keys_r_r:
			val_1 = ripe_dicts[0][item]
			val_2 = ripe_dicts[1][item]
			# print (f'Val 1 is {val_1} and Val 2 is {val_2}')
			merged_val = [val_1[0] + val_2[0], ['r-{}'.format(msm_id[0]), 'r-'.format(msm_id[1])]]
			traceroute_dict[item] = merged_val

		for item in common_keys_r0_c:
			val_1 = ripe_dicts[0][item]
			val_2 = caida_dict[item]
			merged_val = [val_1[0] + val_2[0], ['c-v{}'.format(ip_version), 'r-'.format(msm_id[0])]]
			traceroute_dict[item] = merged_val

		for item in common_keys_r1_c:
			val_1 = ripe_dicts[1][item]
			val_2 = caida_dict[item]
			merged_val = [val_1[0] + val_2[0], ['c-v{}'.format(ip_version), 'r-'.format(msm_id[1])]]
			traceroute_dict[item] = merged_val

		for item in all_common_keys:
			val_1 = ripe_dicts[0][item]
			val_2 = ripe_dicts[1][item]
			val_3 = caida_dict[item]
			merged_val = [val_1[0] + val_2[0] + val_3[0], ['r-{}'.format(msm_id[0]), 'r-'.format(msm_id[1]), 'c-v{}'.format(ip_version)]]
			traceroute_dict[item] = merged_val

  # Deleting processed variables to save memory
		try:
			del(caida_dict)
			del(ripe_dict)
			del(ripe_dicts)
		except:
			pass

		merge_ab_and_ba_links(traceroute_dict, None, 1)

		logger.info('Finally, we have %d traceroute links', len(traceroute_dict))

		# Let's save the entire output and only the links as 2 files
		save_directory = output_path('mapping_outputs')
		save_directory.mkdir(parents=True, exist_ok=True)

		links = list(traceroute_dict.keys())

		save_file = 'full_processed_traceroute_output_v{}'.format(ip_version)

		save_results_to_file(traceroute_dict, str(save_directory), save_file)

		# Let's delete traceroute dict so save memory
		try:
			del(traceroute_dict)
		except:
			pass 

		save_file = 'links_v{}'.format(ip_version)

		save_results_to_file(links, str(save_directory), save_file)

		# Now, let's find all the uniq IPs
		uniq_ips = set()

		for ip_1, ip_2 in links:
			uniq_ips.add(ip_1)
			uniq_ips.add(ip_2)

		uniq_ips_list = list(uniq_ips)

		logger.info('# of uniq IPs: %d', len(uniq_ips_list))

		save_file = 'all_ips_v{}'.format(ip_version)

		save_results_to_file(uniq_ips_list, str(save_directory), save_file)

		return links, uniq_ips_list

	else:
	 # Will be filled later
		return None



def load_all_links_and_ips_data (ip_version=4, source_mode='ripe_only', measurements=None):

	save_directory = output_path('mapping_outputs')
	save_directory.mkdir(parents=True, exist_ok=True)

	links, uniq_ips_list = [], []

	save_file = 'links_v{}'.format(ip_version)

	if Path(save_directory / save_file).is_file():
		with open(save_directory / save_file, 'rb') as fp:
			links = pickle.load(fp)

	save_file = 'all_ips_v{}'.format(ip_version)

	if Path(save_directory / save_file).is_file():
		with open(save_directory / save_file, 'rb') as fp:
			uniq_ips_list = pickle.load(fp)

	if len(links) == 0 or len(uniq_ips_list) == 0:
		if source_mode == 'ripe_only':
			links, uniq_ips_list = generate_links_and_ips_from_ripe_only(ip_version, measurements=measurements)
		else:
			links, uniq_ips_list = generate_links_and_ips_from_all_sources(ip_version)

	return links, uniq_ips_list



def generate_test_case_links_and_ips_data (ip_version=4):

	save_directory = output_path('mapping_outputs')

	save_file = 'test_links_v{}'.format(ip_version)

	if Path(save_directory / save_file).is_file():
  
		with open(save_directory / save_file, 'rb') as fp:
			test_links = pickle.load(fp)

		uniq_ips = set()

		for ip_1, ip_2 in test_links:
			uniq_ips.add(ip_1)
			uniq_ips.add(ip_2)

		uniq_ips_list = list(uniq_ips)

		return test_links, uniq_ips_list

	else:

		save_file = 'links_v{}'.format(ip_version)

		if Path(save_directory / save_file).is_file():
			with open(save_directory / save_file, 'rb') as fp:
				links = pickle.load(fp)

		else:
			logger.error('Full file should be pre-generated to allow test cases to be sampled')
			sys.exit(1)

  # Let's generate 500 random links from these
		test_links = random.sample(links, 500)

		# Let's load like 100 links in each of the 6 categories and let's do it before the update based on haversine distance
		save_file = 'categories_map_v{}'.format(ip_version)

		if Path(save_directory / save_file).is_file():
			with open(save_directory / save_file, 'rb') as fp:
				categories_map = pickle.load(fp)

		else:
			print ('Full file should be pre-generated to allow test cases to be sampled')
			sys.exit(1)

		for category, contents in categories_map.items():
			test_links.extend(random.sample(contents, 100))

		manual_links = [('193.252.137.78', '193.251.132.231'), ('81.253.183.38', '81.52.188.20'), 
		    ('193.253.151.246', '193.253.82.206'), ('142.251.54.131', '108.170.238.33'), 
		    ('209.85.248.171', '108.170.238.32'), ('216.239.63.134', '108.170.237.135'), 
		    ('74.125.252.173', '108.170.237.132'), ('142.250.213.14', '142.251.250.173'), 
		    ('108.170.235.22', '142.251.250.172'), ('108.170.234.13', '142.250.213.194'), 
		    ('142.250.226.150', '142.250.213.211'), ('72.14.237.68', '142.250.226.86'), 
		    ('108.170.234.41', '142.250.226.87'), ('62.115.44.164', '62.115.122.34'), 
		    ('62.115.140.216', '62.115.122.35'), ('62.115.140.214', '62.115.122.33'), 
		    ('62.115.34.133', '62.115.134.238'), ('148.122.10.197', '146.172.105.105'), 
		    ('148.122.10.202', '77.214.52.101'), ('195.89.115.213', '195.2.21.14'), 
		    ('195.2.22.30', '195.2.21.13'), ('213.248.84.32', '62.115.139.196'), 
		    ('62.115.140.214', '62.115.123.27')]


		test_links.extend(manual_links)

		logger.info('Our test links size is %d', len(test_links))

		uniq_ips = set()

		for ip_1, ip_2 in test_links:
			uniq_ips.add(ip_1)
			uniq_ips.add(ip_2)

		uniq_ips_list = list(uniq_ips)

		save_file = 'test_links_v{}'.format(ip_version)

		save_results_to_file(test_links, str(save_directory), save_file)

		return test_links, uniq_ips_list



if __name__ == '__main__':

	load_all_links_and_ips_data(ip_version=4)
 
	#test_links, uniq_ips_list = generate_test_case_links_and_ips_data(ip_version=4)
