import selenium, sys

from selenium.webdriver.common.keys import Keys

from selenium import webdriver
from selenium.webdriver.common.by import By

import time, re, pickle, json, traceback

import warnings
warnings.filterwarnings("ignore")

from bs4 import BeautifulSoup

from pathlib import Path

from collections import namedtuple

from urllib3.exceptions import MaxRetryError

from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException, InvalidSelectorException
from utils.project_paths import log_path, output_path, raw_path, result_path

Location = namedtuple('Location', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network', 'ISP', 'Org'])

def teardown_ipgeolocation_connection (driver):

	try:
		driver.close()
		driver.quit()
	except Exception as e:
		print (f"Couldn't close because of exception {str(e)}")



def setup_ipgeolocation_connection (chromedriver_location, driver=None, mode=0, chromedriver_binary=None):

	chrome_options = Options()
	capabilities = DesiredCapabilities.CHROME
	capabilities["pageLoadStrategy"] = "eager"
	chrome_options.add_argument('--headless')

	if mode == 0:
		chrome_options.add_argument('--no-sandbox')
		chrome_options.binary_location = input('Enter chromedriver binary full path: ')
  
	url = 'https://www.iplocation.net/ip-lookup'

	count = 1

	# Let's try a few times to get the webdriver up and running
	while count < 10:
		if not driver:
			driver = webdriver.Chrome(chromedriver_location, chrome_options = chrome_options, desired_capabilities = capabilities)

		try:
			driver.get(url)

			# There may be some cookies question either as we open or after some time
			try:
				cookieButton = driver.find_element(By.ID, 'ez-accept-all')
				cookieButton.click()
			except:
				pass

   # Let's just load only the required portion of the page, don't waste time waiting for unnecessary web elements to be downloaded
			element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, 'submit')))
			driver.execute_script("window.stop();")

			# There could be cookies question even after opening the page
			try:
				cookieButton = driver.find_element(By.ID, 'ez-accept-all')
				cookieButton.click()
			except:
				pass

			return driver

		except Exception as e:
			print ('Most likely we Timed out !!! Just to be safe, printing the exception below')
			print (f'Got the exception {str(e)}')
			teardown_ipgeolocation_connection(driver)
			driver = None
			time.sleep(count)
			count += 1
			if count > 5:
				chrome_options.add_argument('--disable-dev-shm-usage')
			continue

	return None


def relevant_portions_decoded (item):

	return item.decode().split(':')[-1].strip().encode("ascii")


def transform_list_to_location_namedtuple (result):

	named_list = [relevant_portions_decoded(result[-6]), 
	     relevant_portions_decoded(result[-7]),
	     relevant_portions_decoded(result[-8]), 
	     '', 
	     relevant_portions_decoded(result[-2]), 
	     relevant_portions_decoded(result[-1]), 
	     '', '', 
	     relevant_portions_decoded(result[-4]), 
	     relevant_portions_decoded(result[-3])]

	return Location._make(named_list)


def extract_geolocation_info (data):

	"""
    This function extracts the information in the order country, state, city, ISP, Org, Latitude, Longitude and returns the same
    Inputs
        data -> The list of results by each IP geolocations called by ipgeolocation.net
    """

	result = []
	for item in data:
		soup = BeautifulSoup(item.get_attribute('innerHTML'), 'html.parser')

		# Some locations don't have standard ascii characters, so we replace them to the closest ascii character
		res = [i.text.encode('ascii', 'replace').strip() for i in soup.findAll("div")][1:]
  
		result.append(transform_list_to_location_namedtuple(res))
  
	return result


def check_file_presence (args):

	tags = args.get('tags', 'default')

	save_file = f'ipgeolocation_file_{tags}'
 
	save_directory = output_path('location_data/iplocation_files')

	path = Path(save_directory / save_file)

	if path.is_file():
		return True
	else:
		return False



def save_response_to_file (contents, ip_address, response, args):

	tags = args.get('tags', 'default')
	ip_version = args.get('ip_version', 4)

	save_file = f'ipgeolocation_file_v{ip_version}_{tags}'

	save_directory = output_path('location_data/iplocation_files')

	save_directory.mkdir(parents=True, exist_ok=True)

	contents[ip_address] = response

	print ('Saving response to file')

	with open(save_directory / save_file, 'wb') as fp:
		pickle.dump(contents, fp, protocol=3)



def get_ipgeolocation_response (ip_address, driver, args, contents):

	retry_count = 0

	# Essentially trying a couple of times until we succeed or give up
	while retry_count < 6:

		try:
			try:
				print (f'Retry count now is {retry_count}')
				print ('Input element is being done !!!')
				if retry_count > 1:
					check_input = WebDriverWait(driver, 2).until(EC.presence_of_element_located((By.NAME, 'query')))
				inputElement = driver.find_element(By.NAME, 'query')
				inputElement.clear()
				inputElement.send_keys(str(ip_address))

				try:
					ad_button = driver.find_element(By.CLASS_NAME, 'ezmob-footer-close')
					ad_button.click()
				except:
					pass

				print ('Submit button is being clicked !!!')
				if retry_count > 1:
					check_button = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.NAME, 'submit')))
				button = driver.find_element(By.NAME, 'submit')
				button.click()

				print ('Element is being searched !!! ')
				element = WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "div[class^=geolocation-box]")))
				driver.execute_script("window.stop();")
				data = driver.find_elements(By.CSS_SELECTOR, "div[class^=geolocation-box]")

				# Some time to load everything up
				time.sleep(2)

				response = extract_geolocation_info (data)

				print ('Finished response')

				save_response_to_file(contents, ip_address, response, args)

				return response, contents

			except (NoSuchElementException, TimeoutException)  as e:
				print (f'Encountered error, {type(e).__name__} with message {str(e)}')
				print (f'Sleeping for a while, retry count is {retry_count}')
				time.sleep (2)
				retry_count += 1
				if retry_count % 5 == 0:
					driver = setup_ipgeolocation_connection(driver)

			except MaxRetryError as e:
				print (f'Encountered max retry error, {type(e).__name__} with message {str(e)}')
				retry_count += 1
				if retry_count % 5 == 0:
					driver = setup_ipgeolocation_connection(driver)

			except Exception as e:
				traceback.format_exc()
				retry_count += 1
				print (f'Found the exception {type(e).__name__} with message {str(e)}')
				driver = setup_ipgeolocation_connection (driver)

		except InvalidSelectorException as e:
			print (f"Ignoring {type(e).__name__} with error message {str(e)}")
			if retry_count % 5 == 0:
				retry_count += 1
				driver = setup_ipgeolocation_connection(driver)

		except Exception as e:
			traceback.format_exc()
			retry_count += 1
			print (f'Outer : Found the exception {type(e).__name__} with message {str(e)}')
			driver = setup_ipgeolocation_connection(driver)

	return None, None


def generate_ips_list_to_examine (args, len_single_file=4500):

	tags = args.get('tags', 'default')
	ips_file_directory = args.get('ips_file_directory', None)
	ips_file_prefix = args.get('ips_file_prefix', None) 

	return_args = {k: v for k,v in args.items() if k in ['tags']}

	try:
		ips_indices = args.get('ips_indices', None)

		try:

		 # Let's first check if the start and end index are in same file
			start_file_number = ips_indices[0] // len_single_file
			end_file_number = ips_indices[-1] // len_single_file

			if start_file_number == end_file_number:

			 # Let's format index according to file
				file_formatted_indices = [item % len_single_file for item in ips_indices]

				print (f'File formatted indices are {file_formatted_indices}')

				file_name = f'{ips_file_prefix}_{start_file_number}'

				file_path = Path(ips_file_directory / file_name)

				with open(file_path, 'rb') as fp:
					ips = pickle.load(fp)

				ips_to_examine = [ips[item] for item in range(len(ips)) if item in file_formatted_indices]

				return (ips_to_examine, return_args)

			else:

			 # Looks like our indices are split between 2 files
				ips_to_examine = []

				file_name = f'{ips_file_prefix}_{start_file_number}'
				file_path = Path(ips_file_directory / file_name)

				with open(file_path, 'rb') as fp:
					ips = pickle.load(fp)

				file_formatted_indices = [item % len_single_file for item in ips_indices if item < end_file_number * len_single_file]

				ips_to_examine.extend([ips[item] for item in range(len(ips)) if item in file_formatted_indices])

				file_name = f'{ips_file_prefix}_{end_file_number}'
				file_path = Path(ips_file_directory / file_name)

				with open(file_path, 'rb') as fp:
					ips = pickle.load(fp)

				file_formatted_indices = [item % len_single_file for item in ips_indices if item >= end_file_number * len_single_file]

				ips_to_examine.extend([ips[item] for item in range(len(ips)) if item in file_formatted_indices])

				return (ips_to_examine, return_args)
		except:
			pass
	except:
		pass

	return ([], return_args)



def generate_location_for_list_of_ips (list_of_ips=[], in_chunks=False, args=None, len_single_file=4500):

 # in_chunks is to be used when we have a orchestrator script to control the arguments to be passed to this script
 # Used in the case of multiple-servers being used for geolocation

	ip_count = 0
	chromedriver_location = args.get('chromedriver_location', None)

	if in_chunks:
		chromedriver_binary = args.get('chromedriver_binary', None)
		if chromedriver_location and chromedriver_binary:
			driver = setup_ipgeolocation_connection(chromedriver_location, driver=None, mode=0, chromedriver_binary=chromedriver_binary)
	else:
		driver = setup_ipgeolocation_connection(chromedriver_location, driver=None, mode=1)

	if in_chunks:
		list_of_ips, args = generate_ips_list_to_examine(args, len_single_file)

	if len(list_of_ips) > 0:
		contents = {}

		# Essentially a functionality to continue from where things failed
		if check_file_presence(args):
			print (f'We already had the contents from this file, skipping over !!')
  
		else:
			try:
				while ip_count < len(list_of_ips):

					ip = list_of_ips[ip_count]
					print (f"Currently examining IP : {ip}")

					response, contents = get_ipgeolocation_response(ip, driver, args, contents)

					print (response, end='\n\n')

					if response == None:
						print (f'Looks like we encountered some error. Lets give up !!')
						break

					ip_count += 1

			except Exception as e:
				traceback.format_exc()
				print (f'There seems to be some issue, terminating stuff. We got the error {str(e)}')
				teardown_ipgeolocation_connection(driver)
				exit(1)

	else:
		print ('Please enter either valid list of IPs or send proper arguments')


	teardown_ipgeolocation_connection(driver)



if __name__ == '__main__':

	mode = 1
	args = {}
	list_of_ips = []

	if mode == 0:
		args['ips_indices'] = list(map(int, sys.argv[1].split('-')))
		args['ips_file_directory'] = output_path('ip_data')
		args['ips_file_prefix'] = 'ips_group'
		args['chromedriver_binary'] = input('Enter chromedriver binary location: ')
		args['chromedriver_location'] = input('Enter chromedriver full path: ')
	else:
		args['chromedriver_location'] = input('Enter chromedriver full path: ')
		ip_version = 4
		args['ip_version'] = ip_version
		with open(str(output_path(f'mapping_outputs/all_ips_v{ip_version}')), 'rb') as fp:
			sample_ips_list = pickle.load(fp)
  #list_of_ips = ['66.85.82.9', '156.225.182.1', '67.59.254.241', '103.78.227.1', '193.34.197.140', '23.111.226.1', '193.0.214.1', '152.255.147.235', '216.19.218.1']
		list_of_ips = sample_ips_list[:20]

	if mode == 0:
		generate_location_for_list_of_ips (list_of_ips, in_chunks=True, args=args, len_single_file=4500)
	else:
		generate_location_for_list_of_ips (list_of_ips, in_chunks=False, args=args, len_single_file=4500)

