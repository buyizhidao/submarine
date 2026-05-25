from cymruwhois import Client

from pathlib import Path

import pickle

import os, sys
sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path

from utils.traceroute_utils import load_all_links_and_ips_data


def save_cymru_whois_output (cymru_output, ip_version = 4, tags='default'):

	save_directory = output_path('ip2as_data/')

	save_directory.mkdir(parents=True, exist_ok=True)

	with open(str(output_path('ip2as_data/cymru_whois_output_v{}_{}')).format(ip_version, tags), 'wb') as fp:
		pickle.dump(cymru_output, fp)


def resume_operation (ip_version=4, tags='default'):

	save_directory = output_path('ip2as_data/')
	save_directory.mkdir(parents=True, exist_ok=True)

	save_file = save_directory / 'cymru_whois_output_v{}_{}'.format(ip_version, tags)

	if Path(save_file).exists():
		with open(save_file, 'rb') as fp:
			cymru_output = pickle.load(fp)
		start_index = len(cymru_output)

	else:
		cymru_output = {}
		start_index = 0

	return cymru_output, start_index


def generate_ip2as_for_list_of_ips (ips_list, ip_version = 4, tags='default'):

	cymru_output = {}

	cymru_client = Client()

	cymru_output, start_index = resume_operation(tags)

	count = start_index

	retry_count = 0

	# Sometimes, we have issue with this client, so we use a "while" infinite loop instead of for loop
	while True:
		if len(ips_list) <= start_index:
			print ('Finishing things up here')
			break
		else:
			print (f'Current start index is {start_index}')
			try:
				records = cymru_client.lookupmany(ips_list[start_index:])
				for record in records:
					cymru_output[ips_list[count]] = (record.owner, record.asn)
					count += 1
					if count % 10000 == 0:
						print (f'Processed {count} entries')
				start_index = count
			except Exception as e:
				print (f'Got error : {str(e)}')
				print (f'Currently we have processed {len(cymru_output)} IPs and we have encountered an error')
				print (f'Lets do a partial save with count {count}')

				save_cymru_whois_output(cymru_output, tags)

				# It is possible that this particular IP is causing the issue, let's skip it over
				print (f'We are skipping {ips_list[count]} potentially because it could be the issue')

				count += 1
				start_index = count
				retry_count += 1

				# Maybe there is an issue with the client only, so let's give up
				if retry_count > 10:
					break

	print (f'Doing a final save of what we have currently, where we processed {len(cymru_output)} IPs of {len(ips_list)}')

	save_cymru_whois_output(cymru_output, ip_version, tags)

	return cymru_output


def load_cymru_whois_output(ip_version=4, tags='default', ips_list=[]):

	file_location = str(output_path('ip2as_data/cymru_whois_output_v{}_{}')).format(ip_version, tags)

	if Path(file_location).exists():
		with open(file_location, 'rb') as fp:
			cymru_output = pickle.load(fp)
	else:
		if len(ips_list) > 0:
			cymru_output = generate_ip2as_for_list_of_ips(ips_list, ip_version, tags)
		else:
			print (f'Please enter either valid file tag or ips list')
			return None

	return cymru_output


if __name__ == '__main__':

 #sample_ips_list = ['66.85.82.9', '156.225.182.1', '67.59.254.241', '103.78.227.1', '193.34.197.140', '23.111.226.1', '193.0.214.1', '152.255.147.235', '216.19.218.1']

	_, sample_ips_list = load_all_links_and_ips_data(ip_version=6)

	print (f'Length of IPs data : {len(sample_ips_list)}')

	cymru_output = generate_ip2as_for_list_of_ips(sample_ips_list, 6)

	print (f'We have results for {len(cymru_output)} IPs')

