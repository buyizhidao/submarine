import argparse
import csv
import os
import pickle
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import configure_logging, get_logger

from utils.pickle_compat import Cable, LandingPoints

logger = get_logger(__name__)


def parse_args():
	parser = argparse.ArgumentParser(description='Convert processed submarine CSVs into Nautilus-compatible pickle files.')
	parser.add_argument('--processed-dir', default=str(raw_path('submarine/processed')))
	parser.add_argument('--output-dir', default=str(raw_path('submarine_data')))
	parser.add_argument('--log-dir', default=str(log_path()), help='Directory for automatic run logs.')
	parser.add_argument('--log-level', default='INFO', help='Logging level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.')
	return parser.parse_args()


def read_csv(path):
	with Path(path).open(newline='', encoding='utf-8-sig') as fp:
		return list(csv.DictReader(fp))


def parse_float(value, default=0.0):
	try:
		if value in (None, ''):
			return default
		return float(value)
	except ValueError:
		return default


def parse_int(value, default=0):
	try:
		if value in (None, ''):
			return default
		return int(float(value))
	except ValueError:
		return default


def split_owners(value):
	if not value:
		return []
	return [item.strip() for item in value.split(',') if item.strip()]


def build_pickles(processed_dir):
	processed_dir = Path(processed_dir)
	cables_rows = read_csv(processed_dir / 'cables.csv')
	landing_rows = read_csv(processed_dir / 'landing_points.csv')
	cable_landing_rows = read_csv(processed_dir / 'cable_landing_points.csv')

	landing_base = {}
	for row in landing_rows:
		landing_id = row['landing_point_id']
		landing_base[landing_id] = {
		 'latitude': parse_float(row.get('latitude')),
		 'longitude': parse_float(row.get('longitude')),
		 'country': row.get('country') or '',
		 'location': row.get('name') or landing_id,
		}

	cable_to_landing_ids = defaultdict(list)
	for row in cable_landing_rows:
		cable_to_landing_ids[row['cable_id']].append(row['landing_point_id'])

	cable_info_dict = {}
	owners_dict = defaultdict(list)
	country_dict = defaultdict(list)
	landing_points_dict = {}
	cable_to_connected_location_ids = {}

	for row in cables_rows:
		cable_id = row['cable_id']
		cable_name = row.get('cable_name') or cable_id
		landing_ids = cable_to_landing_ids.get(cable_id, [])
		owners = split_owners(row.get('owners'))

		cable_info_dict[cable_id] = Cable(
		 cable_name,
		 landing_ids,
		 parse_float(row.get('length_km')),
		 owners,
		 '',
		 parse_int(row.get('rfs')),
		 {'status': row.get('status'), 'suppliers': row.get('suppliers'), 'official_url': row.get('official_url')},
		)

		for owner in owners:
			owners_dict[owner].append(cable_id)

		for landing_id in landing_ids:
			base = landing_base.get(landing_id)
			if not base:
				continue
			if landing_id not in landing_points_dict:
				landing_points_dict[landing_id] = LandingPoints(
				 base['latitude'],
				 base['longitude'],
				 base['country'],
				 base['location'],
				 [cable_id],
				)
			elif cable_id not in landing_points_dict[landing_id].cable:
				landing_points_dict[landing_id].cable.append(cable_id)
			if cable_id not in country_dict[base['country']]:
				country_dict[base['country']].append(cable_id)

		cable_to_connected_location_ids[cable_name] = [
		 list(pair) for pair in zip(landing_ids, landing_ids[1:])
		]

	return {
	 'cable_info_dict': cable_info_dict,
	 'owners_dict': dict(owners_dict),
	 'country_dict': dict(country_dict),
	 'landing_points_dict': landing_points_dict,
	 'cable_to_connected_location_ids': cable_to_connected_location_ids,
	}


def main():
	args = parse_args()
	configure_logging(Path(__file__).name, args.log_dir, args.log_level)
	output_dir = Path(args.output_dir)
	output_dir.mkdir(parents=True, exist_ok=True)

	for name, value in build_pickles(args.processed_dir).items():
		with (output_dir / name).open('wb') as fp:
			pickle.dump(value, fp, protocol=pickle.HIGHEST_PROTOCOL)
		logger.info('Wrote %s: %d entries', output_dir / name, len(value))


if __name__ == '__main__':
	try:
		main()
	except Exception:
		logger.exception('convert_submarine_processed_to_nautilus_pickles failed')
		raise
