import argparse
import os
import sys
from pathlib import Path

sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import configure_logging, get_logger

from location.maxmind_utils import generate_locations_for_list_of_ips
from utils.common_utils import generate_cable_mapping, generate_final_mapping, regenerate_categories_map
from utils.merge_data import common_merge_operation
from utils.traceroute_utils import load_all_links_and_ips_data

logger = get_logger(__name__)


def parse_args():
	parser = argparse.ArgumentParser(description='Run RIPE-only, GeoIP-only Nautilus mapping with mode=0.')
	parser.add_argument('--ip-version', type=int, default=4, choices=[4, 6])
	parser.add_argument('--mmdb-file', default=str(raw_path('location_data/GeoLite2-City.mmdb')))
	parser.add_argument('--skip-geoip', action='store_true', help='Use existing maxmind_location_output file.')
	parser.add_argument('--max-links', type=int, default=None, help='Optional cap per category for smoke tests.')
	parser.add_argument('--no-resume', action='store_true', help='Ignore complete category outputs and checkpoint parts.')
	parser.add_argument('--checkpoint-links', type=int, default=50000, help='Number of links per cable-mapping checkpoint part.')
	parser.add_argument('--progress-interval', type=int, default=5000, help='Print progress every N processed links.')
	parser.add_argument('--log-dir', default=str(log_path()), help='Directory for automatic run logs.')
	parser.add_argument('--log-level', default='INFO', help='Logging level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.')
	parser.add_argument('--keep-checkpoints', action='store_true', help='Keep checkpoint part files after complete category outputs are verified.')
	return parser.parse_args()


def run(args):
	links, all_ips = load_all_links_and_ips_data(ip_version=args.ip_version, source_mode='ripe_only')
	logger.info('Loaded %d RIPE-only links and %d unique IPs', len(links), len(all_ips))

	if not args.skip_geoip:
		locations, skipped = generate_locations_for_list_of_ips(
		 all_ips,
		 ip_version=args.ip_version,
		 mmdb_file=args.mmdb_file,
		)
		if locations is None:
			raise FileNotFoundError(f'Missing mmdb file: {args.mmdb_file}')
		logger.info('Generated GeoIP locations for %d IPs; skipped %d IPs', len(locations), len(skipped))

	max_links_to_process = None
	if args.max_links is not None:
		max_links_to_process = {
		 'bg_oc': args.max_links,
		 'og_oc': args.max_links,
		 'bb_oc': args.max_links,
		 'bg_te': args.max_links,
		 'og_te': args.max_links,
		 'bb_te': args.max_links,
		}

	generate_cable_mapping(
	 mode=0,
	 ip_version=args.ip_version,
	 source_mode='ripe_only',
	 geo_source_mode='maxmind_only',
	 use_owner_score=False,
	 max_links_to_process=max_links_to_process,
		resume=not args.no_resume,
		checkpoint_interval=args.checkpoint_links,
		progress_interval=args.progress_interval,
		cleanup_checkpoints=not args.keep_checkpoints,
	)

	common_merge_operation(str(output_path('mapping_outputs')), 1, [], [f'v{args.ip_version}'], True, None)
	generate_final_mapping(mode=0, ip_version=args.ip_version)
	regenerate_categories_map(mode=0, ip_version=args.ip_version)

	output = Path(str(result_path(f'mapping_outputs/link_to_cable_and_score_mapping_v{args.ip_version}')))
	logger.info('Finished RIPE-only mode=0 mapping. Output: %s', output)


def main():
	args = parse_args()
	configure_logging(Path(__file__).name, args.log_dir, args.log_level)
	try:
		run(args)
	except Exception:
		logger.exception('run_mapping_mode0 failed')
		raise


if __name__ == '__main__':
	main()
