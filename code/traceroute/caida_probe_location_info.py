from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
import json, time, pickle, requests
from geopy.geocoders import Nominatim
from pathlib import Path

import warnings
from utils.project_paths import log_path, output_path, raw_path, result_path
warnings.filterwarnings("ignore")

def get_probe_info_from_webpage():

	chromedriver = input('Enter chromedriver full path: ')
	chrome_options = Options()
	chrome_options.add_argument('--headless')

	url = 'https://www.caida.org/projects/ark/locations/'

	driver = webdriver.Chrome(chromedriver, chrome_options=chrome_options)

	driver.get(url)

	time.sleep(5)

	required_elements = driver.find_elements(By.CSS_SELECTOR, 'tr[id^=montr_]')

	probe_to_location_map = {}

	for element in required_elements:
		soup = BeautifulSoup(element.get_attribute('innerHTML'), 'html.parser')
		td_elements = soup.find_all('td')
		probe_to_location_map[td_elements[0].text.encode("ascii", "ignore").decode()] = td_elements[2].text + ', ' + td_elements[3].text

	driver.close()
	driver.quit()

	return probe_to_location_map


def convert_location_to_coordinates (probe_to_location_map):

	geolocator = Nominatim(user_agent='caidaprobe')
	probe_to_coordinates_map = {}

	for key, location in probe_to_location_map.items():
		coordinate = geolocator.geocode(location)
		probe_to_coordinates_map[key] = tuple((coordinate.latitude, coordinate.longitude))

 # Looks like hlz-nz is missing in the webpage, let's add manually
	probe_to_coordinates_map['hlz-nz'] = (-37.8662, 175.3361)

	# Some missed location for v6
	missed_probes = ['san-us', 'nrn-nl', 'ory4-fr', 'per2-au', 'yyc-ca', 'cld4-us', 'lax3-us', 'hlz2-nz', 'beg-rs', 'wlg-nz', 'gva-ch', 'cld6-us', 'yhu-ca']

	for probe in missed_probes:
		print (f'Original probe: {probe}')
  
		try:
			url = f'https://www.caida.org/projects/ark/statistics/monitor/{probe}/nonresp_as_path_length_ccdf_v6.html'
			r = requests.get(url)
			soup = BeautifulSoup(r.text, 'html.parser')
			location = soup.find_all(id = 'monitorlocation')[0].text.split('(')[0].strip()
		except:
			re_probe = ''.join([item for item in probe if not item.isdigit()])
			print (f'Searching for probe {re_probe}')
			url = f'https://www.caida.org/projects/ark/statistics/monitor/{re_probe}/nonresp_as_path_length_ccdf_v6.html'
			r = requests.get(url)
			soup = BeautifulSoup(r.text, 'html.parser')
			location = soup.find_all(id = 'monitorlocation')[0].text.split('(')[0].strip()
  
		coordinate = geolocator.geocode(location)
		print (f'For {probe}, we got {coordinate}')
		probe_to_coordinates_map[probe] = tuple((coordinate.latitude, coordinate.longitude))


	return probe_to_coordinates_map


def save_probe_to_coordinate_map (probe_to_coordinates_map):

	with open(str(output_path('all_caida_probe_names_with_coordinates')), 'wb') as fp:
		pickle.dump(probe_to_coordinates_map, fp)


def load_probe_to_coordinate_map():

	if Path(output_path('all_caida_probe_names_with_coordinates')).exists():
		with open(str(output_path('all_caida_probe_names_with_coordinates')), 'rb') as fp:
			probe_to_coordinates_map = pickle.load(fp)
	else:
		probe_to_location_map = get_probe_info_from_webpage()
		probe_to_coordinates_map = convert_location_to_coordinates(probe_to_location_map)
		save_probe_to_coordinate_map(probe_to_coordinates_map)

	return probe_to_coordinates_map


if __name__ == '__main__':

	probe_to_coordinates_map = load_probe_to_coordinate_map()

	print (json.dumps(probe_to_coordinates_map, indent=4))