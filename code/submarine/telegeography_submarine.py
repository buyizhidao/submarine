
import json
from pathlib import Path

import re

import pickle

from collections import namedtuple

from sklearn.neighbors import BallTree
import math
from utils.pickle_compat import load_pickle
from utils.project_paths import log_path, output_path, raw_path, result_path

telegeography_directory = output_path('submarine-cable-map')  

Cable = namedtuple('Cable', ['name', 'landing_points', 'length', 'owners', 'notes', 'rfs', 'other_info'])

LandingPoints = namedtuple('LandingPoints', ['latitude', 'longitude', 'country', 'location', 'cable'])

save_directory = raw_path('submarine_data')

def get_all_cable_id():
	"""
	This function goes through all.json file, to get the paths for all the cables
	Output
		A list of tuples with each tuple containing the cable id and the corresponding path for that cable
	"""

	p = telegeography_directory / 'v2/cable/all.json'
	with open(p) as f:
		data = json.load(f)

	return [(item['cable_id'], telegeography_directory / 'v2/cable/' / (item['id'] + '.json')) for item in data]


def process_single_file (data, cable_info_dict, country_dict, owners_dict, landing_points_dict):

	"""
	This function essentially processes a single file, puts the content into the cables, countries, owners and landing points 
	dictionaries accordfingly
	Input
		data -> The contents of a cable json file
		cable_info_dict -> A dictionary containing relevant information about the cables
		country_dict -> A dictionary where every key is a country and value is a list of cable id's in that country
		owners_dict -> A dictionary where every key is a owner and value is a list of cable id's owned by that corporation
		landing_points_dict -> A dictionary which contains information of the landing points where each key is a landing point id
	Output
		None
	"""

	for item in data.keys():

		if item == 'cable_id':
			cable_id = data[item]

		elif item == 'length':
			if data[item] != 'n.a.':
			 # This removes the km at the end
				cable_length = float(data[item][:-3].replace(',', ''))
			else:
				cable_length = 0

		elif item == 'rfs':
			if data[item] != 'n.a.':
				rfs = int(re.search(r'\d+', data[item]).group())
			else:
				rfs = 0

		elif item == 'owners':
			owners = [item.strip() for item in data[item].split(',')]
			for owner in owners:

			 # Add the cable to the owner
				owners_dict[owner] = owners_dict.get(owner, [])
				owners_dict[owner].append(cable_id)

		elif item == 'landing_points':
			landing_points = []
			for l in data[item]:
				l_id = l['landing_point_id']
				landing_points.append(l_id)

				if l_id not in landing_points_dict.keys():
					latlon = [float(item.strip()) for item in l['latlon'].split(',')]
					name = l['name']
					country = name.split(',')[-1].strip()

					# Add the cable to the country
					country_dict[country] = country_dict.get(country, [])
					country_dict[country].append(cable_id)

					landing_points_dict[l_id] = LandingPoints(latlon[0], latlon[1], country, name, [cable_id])
				else:
					landing_points_dict[l_id].cable.append(cable_id)

		elif item == 'name':
			cable_name = data[item]

		elif item == 'notes':
			if data['notes'] != None:
				notes = data['notes']
			else:
				notes = ''

	cable_info_dict[cable_id] = Cable(cable_name, landing_points, cable_length, owners, notes, rfs, '')

def process_all_files (cables):

	"""
	This function processes all the cable files found from all.json and opens them up and calls the process_single_file function.
	Additionally, it saves all the information from the various dictions into binary files under the data/intermediate directory
	Input
		cables -> The output from get_all_cables_id() function
	Output
		cable_info_dict -> A dictionary containing relevant information about the cables
		country_dict -> A dictionary where every key is a country and value is a list of cable id's in that country
		owners_dict -> A dictionary where every key is a owner and value is a list of cable id's owned by that corporation
		landing_points_dict -> A dictionary which contains information of the landing points where each key is a landing point id
	"""

	cable_info_dict = {}
	country_dict = {}
	owners_dict = {}
	landing_points_dict = {}

	for cable in cables:
		try:
			with open(cable[1]) as f:
				data = json.load(f)
    
				process_single_file(data, cable_info_dict, country_dict, owners_dict, landing_points_dict)

		except Exception as e:

			print (f'Failed for cable {cable[0]} or {cable[1]}')
			print (e)
			print ()

	save_directory.mkdir(parents=True, exist_ok=True)

	with open(save_directory / 'cable_info_dict', 'wb') as fp:
		pickle.dump(cable_info_dict, fp)

	with open(save_directory / 'country_dict', 'wb') as fp:
		pickle.dump(country_dict, fp)

	with open(save_directory / 'owners_dict', 'wb') as fp:
		pickle.dump(owners_dict, fp)

	with open(save_directory / 'landing_points_dict', 'wb') as fp:
		pickle.dump(landing_points_dict, fp)

	return (cable_info_dict, country_dict, owners_dict, landing_points_dict)


def get_cables_by_country (country):

	"""
	These are queries to get list of all cable id's within a country.
	Input
		country -> A country name given as string
	Output
		A list of all the cable id's in that country
	TODO : Integrate language module to match partial names for countries 
	"""
 
	with open(save_directory / 'country_dict', 'rb') as fp:
		country_dict = load_pickle(fp)

	country_list = list(country_dict.keys())

	retval = []

	for con in country_list:
		if country.lower() in con.lower():
			retval.append(country_dict[con])

	retval = set([int(i) for i in str(retval).replace('[', '').replace(']', '').split(', ')])

	return retval


def get_cables_by_owner (owner):

	"""
	These are queries to get list of all cable id's owned by a corporation.
	Input
		owner -> A owner name given as string
	Output
		A list of all the cable id's in that owner
	TODO : Integrate language module to match partial names for owners 
	"""
 
	with open(save_directory / 'owners_dict', 'rb') as fp:
		owners_dict = load_pickle(fp)

	owners_list = list(owners_dict.keys())

	retval = []

	for own in owners_list:
		if owner.lower() in own.lower():
			retval.append(owners_dict[own])

	retval = set([int(i) for i in str(retval).replace('[', '').replace(']', '').split(', ')])

	return retval

def get_all_owners ():

	with open(save_directory / 'owners_dict', 'rb') as fp:
		owners_dict = load_pickle(fp)

	owners_list = list(owners_dict.keys())

	return owners_list

def find_intersecting_cables (owner_cables, country_cables):

	"""
	This function is essentially used to find the intersection between 2 lists of cable id
	Typically would be used to find intersection of owner cables with country cables
	"""
	return (list(set(owner_cables) & set(country_cables)))

def get_cable_by_cable_id (cable_id):

	"""
	These are queries to get info about a cable from it's cable id.
	Input
		cable_id -> A cable id given as an integer
	Output
		information about the cable as stored in the Cable NamedTuple format 
	"""

	with open(save_directory / 'cable_info_dict', 'rb') as fp:
		cable_info_dict = load_pickle(fp)

	if cable_id in cable_info_dict.keys():
		return cable_info_dict[cable_id]

def get_landing_points_by_id (landing_points_id):

	"""
	These are queries to get info about a landing point from it's landing point id.
	Input
		landing_point_id -> A landing point id given as an integer
	Output
		information about the landing point as stored in the LandingPoint NamedTuple format 
	"""

	with open(save_directory / 'landing_points_dict', 'rb') as fp:
		landing_points_dict = load_pickle(fp)

	if landing_points_id in landing_points_dict.keys():
		return landing_points_dict[landing_points_id]


def get_all_latlon_locations_ball_tree ():
    
    with open(save_directory / 'landing_points_dict', 'rb') as fp:
        landing_points_dict = load_pickle(fp)
    
    latlon_dict = {}
    for key, value in landing_points_dict.items():
    	latlon_dict[(value.latitude, value.longitude)] = key
    
    latlons = list(latlon_dict.keys())

    latlons_in_radians = list(map(convert_degrees_to_randians, latlons))

    tree = BallTree(latlons_in_radians, metric = "haversine", leaf_size=2)
    
    return (landing_points_dict, latlon_dict, latlons, tree)


def convert_degrees_to_randians(item):
    return tuple(map(math.radians, item))

def list_conversion_from_array (array):
	return [i.tolist() for i in array]


def get_landing_points_cables_near_location (fixed_point, tree, landing_points_dict, latlon_dict, latlons):

	initial_distance = 50
	increase_distance = 50
	ind = [[]]
	converted_fixed_point = [convert_degrees_to_randians(fixed_point)]

	# print ('Using the updated version 3')

	while len(ind[0]) < 3:
		ind, dist = map(list_conversion_from_array, tree.query_radius(converted_fixed_point, initial_distance/6371, return_distance=True))
		initial_distance += increase_distance

	cables = []
	landing_points = []

	for i in range(len(ind[0])):
		landing_point = landing_points_dict[latlon_dict[latlons[ind[0][i]]]]
		cables.append(landing_point.cable)
		landing_points.append(landing_point)

	return (dist, ind, cables, landing_points)


if __name__ == '__main__':

	cables = get_all_cable_id()

	cable_info_dict, country_dict, owners_dict, landing_points_dict = process_all_files (cables)
