import logging
import sys
from datetime import datetime
from pathlib import Path

from utils.project_paths import log_path


class ScriptNameFilter(logging.Filter):
	def __init__(self, script_name):
		super().__init__()
		self.script_name = script_name

	def filter(self, record):
		record.script_name = self.script_name
		return True


def configure_logging(script_name, log_dir=None, level='INFO'):
	log_dir = Path(log_dir) if log_dir else log_path()
	log_dir.mkdir(parents=True, exist_ok=True)

	log_level = getattr(logging, str(level).upper(), logging.INFO)
	timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
	log_file = log_dir / f'{Path(script_name).stem}_{timestamp}.log'

	formatter = logging.Formatter(
		'%(asctime)s | %(levelname)s | %(script_name)s | %(name)s:%(funcName)s:%(lineno)d | %(message)s',
		datefmt='%Y-%m-%d %H:%M:%S',
	)

	script_filter = ScriptNameFilter(Path(script_name).name)

	console_handler = logging.StreamHandler(sys.stdout)
	console_handler.setFormatter(formatter)
	console_handler.addFilter(script_filter)

	file_handler = logging.FileHandler(log_file, encoding='utf-8')
	file_handler.setFormatter(formatter)
	file_handler.addFilter(script_filter)

	root_logger = logging.getLogger()
	root_logger.handlers.clear()
	root_logger.setLevel(log_level)
	root_logger.addHandler(console_handler)
	root_logger.addHandler(file_handler)

	logging.captureWarnings(True)
	logger = logging.getLogger(__name__)
	logger.info('Logging to %s', log_file)
	return log_file


def get_logger(name):
	return logging.getLogger(name)
