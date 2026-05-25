from pathlib import Path


CODE_DIR = Path(__file__).resolve().parents[1]
MAPPING_ROOT = CODE_DIR.parent
RAW_DATA_DIR = MAPPING_ROOT / 'data' / 'raw'
INTERMEDIATE_DIR = MAPPING_ROOT / 'data' / 'intermediate'
RESULTS_DIR = MAPPING_ROOT / 'data' / 'results'
OUTPUTS_DIR = INTERMEDIATE_DIR
LOGS_DIR = MAPPING_ROOT / 'logs'


def _join(base, *parts):
	path = base
	for part in parts:
		if part is None or str(part) == '':
			continue
		path = path / str(part)
	return path


def raw_path(*parts):
	return _join(RAW_DATA_DIR, *parts)


def output_path(*parts):
	return intermediate_path(*parts)


def intermediate_path(*parts):
	return _join(INTERMEDIATE_DIR, *parts)


def result_path(*parts):
	return _join(RESULTS_DIR, *parts)


def log_path(*parts):
	return _join(LOGS_DIR, *parts)


def legacy_path(path):
	normalized = str(path).replace('\\', '/')
	if normalized == 'stats':
		return output_path()
	if normalized.startswith('stats/'):
		return output_path(normalized[len('stats/'):])
	if normalized == 'logs':
		return log_path()
	if normalized.startswith('logs/'):
		return log_path(normalized[len('logs/'):])
	if normalized.startswith('../data/submarine/'):
		return raw_path('submarine', normalized[len('../data/submarine/'):])
	if normalized == '../data/submarine':
		return raw_path('submarine')
	if normalized.startswith('../data/geoip/'):
		return raw_path('geoip', normalized[len('../data/geoip/'):])
	if normalized == '../data/geoip':
		return raw_path('geoip')
	return Path(path)
