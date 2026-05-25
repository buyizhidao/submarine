import argparse
import os
import sys
import zipfile
from pathlib import Path

import requests
import geopandas as gpd
from utils.project_paths import log_path, output_path, raw_path, result_path
from utils.logging_utils import configure_logging, get_logger

IPUMSI_URL = 'https://international.ipums.org/international/resources/gis/IPUMSI_world_release2020.zip'
IPUMSI_FEATURE_SERVICE_QUERY = (
 'https://services2.arcgis.com/IsDCghZ73NgoYoz5/ArcGIS/rest/services/world_countries_2020/FeatureServer/0/query'
)

logger = get_logger(__name__)


def parse_args():
	parser = argparse.ArgumentParser(description='Download and unpack the IPUMSI country boundary shapefile expected by Nautilus.')
	parser.add_argument('--url', default=IPUMSI_URL)
	parser.add_argument('--feature-service-url', default=IPUMSI_FEATURE_SERVICE_QUERY)
	parser.add_argument('--stats-dir', default=str(raw_path()))
	parser.add_argument('--log-dir', default=str(log_path()), help='Directory for automatic run logs.')
	parser.add_argument('--log-level', default='INFO', help='Logging level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.')
	return parser.parse_args()


def read_feature_service(url, page_size=100):
	features = []
	offset = 0
	while True:
		params = {
		 'where': '1=1',
		 'outFields': '*',
		 'outSR': '4326',
		 'f': 'geojson',
		 'resultOffset': offset,
		 'resultRecordCount': page_size,
		 'geometryPrecision': 4,
		 'maxAllowableOffset': 0.01,
		}
		logger.info('Reading FeatureServer records %d..%d', offset, offset + page_size - 1)
		response = requests.get(url, params=params, timeout=120)
		response.raise_for_status()
		payload = response.json()
		page_features = payload.get('features', [])
		if not page_features:
			break
		features.extend(page_features)
		if len(page_features) < page_size:
			break
		offset += page_size

	return gpd.GeoDataFrame.from_features(features, crs='EPSG:4326')


def main():
	args = parse_args()
	configure_logging(Path(__file__).name, args.log_dir, args.log_level)
	stats_dir = Path(args.stats_dir)
	zip_path = stats_dir / 'IPUMSI_world_release2020.zip'
	output_dir = stats_dir / 'IPUMSI_world_release2020'
	shp_file = output_dir / 'world_countries_2020.shp'

	if shp_file.exists():
		logger.info('IPUMSI shapefile already exists: %s', shp_file)
		return

	stats_dir.mkdir(parents=True, exist_ok=True)

	try:
		logger.info('Downloading %s', args.url)
		response = requests.get(args.url, timeout=120)
		response.raise_for_status()
		zip_path.write_bytes(response.content)

		logger.info('Extracting %s to %s', zip_path, output_dir)
		output_dir.mkdir(parents=True, exist_ok=True)
		with zipfile.ZipFile(zip_path) as archive:
			archive.extractall(output_dir)
	except requests.HTTPError as exc:
		if exc.response is None or exc.response.status_code != 404:
			raise
		logger.warning('IPUMSI zip URL returned 404; using the official IPUMS ArcGIS FeatureServer fallback')
		output_dir.mkdir(parents=True, exist_ok=True)
		gdf = read_feature_service(args.feature_service_url)
		if 'CNTRY_CODE' not in gdf.columns:
			raise ValueError('FeatureServer output does not include required CNTRY_CODE field')
		gdf.to_file(shp_file)

	if not shp_file.exists():
		raise FileNotFoundError(f'Expected shapefile not found after extraction: {shp_file}')

	logger.info('Prepared IPUMSI shapefile: %s', shp_file)


if __name__ == '__main__':
	try:
		main()
	except Exception:
		logger.exception('prepare_ipumsi_boundaries failed')
		raise
