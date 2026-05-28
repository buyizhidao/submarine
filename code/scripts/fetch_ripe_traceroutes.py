import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(1, os.path.abspath('.'))
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import configure_logging, get_logger

from traceroute.ripe_traceroute_utils import ripe_process_traceroutes

logger = get_logger(__name__)


def parse_args():
	parser = argparse.ArgumentParser(description='Fetch and process RIPE Atlas traceroutes for Nautilus RIPE-only mapping.')
	parser.add_argument('--start', required=True, help='Start time in UTC. Accepts YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DDTHH:MM, or seconds variants.')
	parser.add_argument('--end', required=True, help='End time in UTC. Accepts YYYY-MM-DD, YYYY-MM-DD HH:MM, YYYY-MM-DDTHH:MM, or seconds variants.')
	parser.add_argument('--ip-version', type=int, default=4, choices=[4, 6])
	parser.add_argument('--measurements', nargs='+', default=['5051', '5151'])
	parser.add_argument('--chunk-hours', type=float, default=1.0, help='RIPE API request window size. Smaller values avoid huge responses.')
	parser.add_argument('--no-resume', action='store_true', help='Ignore existing RIPE resume state and start from the beginning.')
	parser.add_argument('--log-dir', default=str(log_path()), help='Directory for automatic run logs.')
	parser.add_argument('--log-level', default='INFO', help='Logging level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.')
	return parser.parse_args()


def parse_date(value):
	value = value.strip()
	formats = [
	 '%Y-%m-%d',
	 '%Y-%m-%d %H:%M',
	 '%Y-%m-%d %H:%M:%S',
	 '%Y-%m-%dT%H:%M',
	 '%Y-%m-%dT%H:%M:%S',
	]
	for date_format in formats:
		try:
			return datetime.strptime(value, date_format)
		except ValueError:
			pass
	raise ValueError(
	 f'Invalid datetime "{value}". Use YYYY-MM-DD, "YYYY-MM-DD HH:MM", '
	 'YYYY-MM-DDTHH:MM, or include seconds.'
	)


def fetch_measurement(args, start_time, end_time, measurement):
	logger.info('Fetching RIPE Atlas measurement %s from %s to %s', measurement, args.start, args.end)
	result = ripe_process_traceroutes(
	 start_time,
	 end_time,
	 str(measurement),
	 args.ip_version,
	 False,
	 chunk_hours=args.chunk_hours,
	 resume=not args.no_resume,
	)
	logger.info('Measurement %s produced %d unique links', measurement, len(result))
	return measurement, len(result)


def main():
	args = parse_args()
	configure_logging(Path(__file__).name, args.log_dir, args.log_level)
	start_time = parse_date(args.start)
	end_time = parse_date(args.end)

	if end_time <= start_time:
		raise ValueError('--end must be later than --start')

	Path(str(output_path('ripe_data'))).mkdir(parents=True, exist_ok=True)

	measurements = [str(measurement) for measurement in args.measurements]
	max_workers = min(2, len(measurements))
	with ThreadPoolExecutor(max_workers=max_workers) as executor:
		futures = {
		 executor.submit(fetch_measurement, args, start_time, end_time, measurement): measurement
		 for measurement in measurements
		}
		for future in as_completed(futures):
			measurement = futures[future]
			try:
				future.result()
			except Exception:
				logger.exception('RIPE Atlas measurement %s failed', measurement)
				raise


if __name__ == '__main__':
	try:
		main()
	except Exception:
		logger.exception('fetch_ripe_traceroutes failed')
		raise
