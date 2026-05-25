import argparse
import os
import pickle
import sys
from pathlib import Path

sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import configure_logging, get_logger

from location.maxmind_utils import generate_locations_for_list_of_ips

logger = get_logger(__name__)


def parse_args():
	parser = argparse.ArgumentParser(description='Generate Nautilus-compatible GeoIP output from a DB-IP/MaxMind mmdb.')
	parser.add_argument('--ip-version', type=int, default=4, choices=[4, 6])
	parser.add_argument('--mmdb-file', default=str(raw_path('location_data/GeoLite2-City.mmdb')))
	parser.add_argument('--tags', default='default')
	parser.add_argument('--log-dir', default=str(log_path()), help='Directory for automatic run logs.')
	parser.add_argument('--log-level', default='INFO', help='Logging level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.')
	return parser.parse_args()


def main():
	args = parse_args()
	configure_logging(Path(__file__).name, args.log_dir, args.log_level)
	all_ips_file = Path(str(output_path(f'mapping_outputs/all_ips_v{args.ip_version}')))
	if not all_ips_file.exists():
		raise FileNotFoundError(f'Missing {all_ips_file}; generate RIPE links/all_ips first')

	with all_ips_file.open('rb') as fp:
		ips = pickle.load(fp)

	Path(str(output_path('location_data'))).mkdir(parents=True, exist_ok=True)
	locations, skipped = generate_locations_for_list_of_ips(
	 ips,
	 ip_version=args.ip_version,
	 tags=args.tags,
	 mmdb_file=args.mmdb_file,
	)

	if locations is None:
		raise FileNotFoundError(f'Missing mmdb file: {args.mmdb_file}')

	logger.info('Generated GeoIP locations for %d IPs; skipped %d IPs', len(locations), len(skipped))


if __name__ == '__main__':
	try:
		main()
	except Exception:
		logger.exception('generate_geoip_locations failed')
		raise
