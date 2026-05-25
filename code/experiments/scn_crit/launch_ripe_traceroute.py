import pickle, subprocess, sys, time, json

from pathlib import Path
sys.path.insert(1, str(Path(__file__).resolve().parents[2]))

from ripe.atlas.cousteau import (Traceroute, AtlasSource, AtlasCreateRequest)

from subprocess import check_output

from collections import namedtuple
from utils.project_paths import log_path, output_path, raw_path, result_path

TraceRoute = namedtuple('TraceRoute', ['hops', 'other_info'])

Hops = namedtuple('Hops', ['hop', 'ip_address', 'rtt'])

# First let's load the country website map

websites_country_map_file = output_path('websites_country_map')
if Path(websites_country_map_file).exists():
	with open(websites_country_map_file, 'rb') as fp:
		websites_country_map = pickle.load(fp)
else:
	try:
		with open('experiments/scn_crit/alexa_top_50_20200215.json') as fp:
			data = json.load(fp)
		websites_country_map = {}
		for country, contents in data.items():
			country_websites = []
			for sites in contents:
				country_websites.append(sites['Site'])
			websites_country_map[country] = country_websites

		with open(websites_country_map_file, 'wb') as fp:
			pickle.dump(websites_country_map, fp)
	except:
		print (f'Top 50 websites file not found. Download from the original SCN-Crit paper')
		sys.exit(1)

# Sanity checking the file

if len(websites_country_map) != 63 or len(websites_country_map['IN']) != 50:
	sys.exit(1)

# The ripe-atlas command

ripe_atlas_command_str = 'ripe-atlas measure traceroute --target {} --from-country {} --probes 1 --auth 8e674566-3a92-42d5-9af0-a67ce38db07a --resolve-on-probe --paris 16 --set-alias ashwin50websites{}{}'

exp_count = 0

for count, (country, websites) in enumerate(websites_country_map.items()):
	print (country)
	for website_count, website in enumerate(websites):
		cmd_str = ripe_atlas_command_str.format(website, country, country.lower(), website_count)
		cmd_str_list = cmd_str.split()
		exp_count += 1
		print (cmd_str_list)
		print ()
		p = subprocess.Popen(cmd_str_list, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
	if count >= 0:
		break
 
print (exp_count)

save_path = Path.cwd() / 'experiments/50_websites/measurement_ids_result'

ripe_key = input('Enter RIPE key: ')

if save_path.is_file():
	with open(save_path, 'rb') as fp:
		result_measurements = pickle.load(fp)
else:
	result_measurements = {}

for count, (country, websites) in enumerate(websites_country_map.items()):
	print (country)
	for website_count, website in enumerate(websites):
		key = f'{country}{website_count}'
		if key in result_measurements:
			print (f'Already performed this measurement for {key}')
		else:
			probe = AtlasSource(type = 'country', value = country, requested = 1)
			description_string = f'ashwin measurement {country.lower()} {website_count}'
			measurement = Traceroute(af = 4, target = website, paris = 16, resolve_on_probe = True, description = description_string, protocol = 'ICMP')
			request = AtlasCreateRequest(key = ripe_key, measurements = [measurement], sources = [probe], is_oneoff = True)
			success, response = request.create()
			exp_count += 1
			if success:
				result_measurements[key] = response['measurements']
				print (response['measurements'])
			else:
				print (f'Failed for {website} in country {country}')

	if count >= 0:
		break

print (exp_count)

with open(save_path, 'wb') as fp:
	pickle.dump(result_measurements, fp)

print ('Measurement file saved')

save_path = Path.cwd() / 'experiments/50_websites/measurement_ids_result'

with open(save_path, 'rb') as fp:
	result_measurements = pickle.load(fp)

all_traceroutes = []

all_traceroutes_dict = {}

for count, (key, measurement_id) in enumerate(result_measurements.items()):
	traceroute_output = check_output(['ripe-atlas', 'report', str(measurement_id[0])], stderr = subprocess.PIPE)
	traceroute_output_decoded = traceroute_output.decode().split('\n')
	all_hops = []
	try:
		probe_info = traceroute_output_decoded[1].split('#')[1]
		hops_info = traceroute_output_decoded[4:-1]
		for hop in hops_info:
			hop_info = hop.strip().replace('ms', '').split()
			hop_number = hop_info[0]
			hop_ip = hop_info[1]
			hop_rtt = hop_info[2:]
			all_hops.append(Hops(hop_number, hop_ip, hop_rtt))
	except:
		pass
 
	if len(all_hops) > 0:
		all_traceroutes.append(TraceRoute(all_hops, {'probe_id': probe_info}))
		all_traceroutes_dict[key] = TraceRoute(all_hops, {'probe_id': probe_info})

	if count % 100 == 0:
		print (f'{count} traceroutes processed')

with open(Path.cwd() / 'experiments/50_websites/traceroutes_info', 'wb') as fp:
	pickle.dump(all_traceroutes, fp)

with open(Path.cwd() / 'experiments/50_websites/traceroutes_info_dict', 'wb') as fp:
	pickle.dump(all_traceroutes_dict, fp)
