import hashlib
import json
import time
from pathlib import Path

import requests


class NautilusApiClient:
	def __init__(self, base_url, cache_dir, rate_limit_seconds=1.0, timeout=60, retries=3):
		self.base_url = base_url.rstrip('/')
		self.cache_dir = Path(cache_dir)
		self.cache_dir.mkdir(parents=True, exist_ok=True)
		self.rate_limit_seconds = rate_limit_seconds
		self.timeout = timeout
		self.retries = retries
		self.session = requests.Session()
		self.last_request_time = 0

	def _sleep_for_rate_limit(self):
		elapsed = time.time() - self.last_request_time
		if elapsed < self.rate_limit_seconds:
			time.sleep(self.rate_limit_seconds - elapsed)

	def _request(self, method, url, **kwargs):
		last_error = None
		for attempt in range(1, self.retries + 1):
			try:
				self._sleep_for_rate_limit()
				response = self.session.request(method, url, timeout=self.timeout, **kwargs)
				self.last_request_time = time.time()
				if response.status_code >= 500 and attempt < self.retries:
					time.sleep(attempt)
					continue
				return response
			except requests.RequestException as exc:
				last_error = exc
				if attempt < self.retries:
					time.sleep(attempt)
		raise RuntimeError(f'Nautilus API request failed: {last_error}')

	def _cache_path(self, sample_id, label):
		safe_id = hashlib.sha1(sample_id.encode('utf-8')).hexdigest()[:16]
		return self.cache_dir / f'{safe_id}_{label}.json'

	def _load_cache(self, sample_id, label):
		path = self._cache_path(sample_id, label)
		if path.exists():
			with path.open(encoding='utf-8') as fp:
				return json.load(fp)
		return None

	def _save_cache(self, sample_id, label, payload):
		path = self._cache_path(sample_id, label)
		with path.open('w', encoding='utf-8') as fp:
			json.dump(payload, fp, ensure_ascii=False, indent=2)

	def submit_traceroute(self, sample_id, traceroute_text):
		cached = self._load_cache(sample_id, 'submit')
		if cached:
			return cached

		payloads = [
			{'traceroute': traceroute_text},
			{'text': traceroute_text},
			{'raw': traceroute_text},
		]
		errors = []
		for payload in payloads:
			response = self._request('POST', f'{self.base_url}/api/traceroute', json=payload)
			record = {
				'status_code': response.status_code,
				'payload_key': next(iter(payload.keys())),
				'text': response.text,
			}
			try:
				record['json'] = response.json()
			except ValueError:
				record['json'] = None
			if 200 <= response.status_code < 300:
				self._save_cache(sample_id, 'submit', record)
				return record
			errors.append(record)

		record = {'status_code': None, 'errors': errors}
		self._save_cache(sample_id, 'submit', record)
		return record

	def _candidate_ids(self, submit_record):
		ids = [None]
		payload = submit_record.get('json')

		def visit(obj):
			if isinstance(obj, dict):
				for key, value in obj.items():
					if key.lower() in ['id', 'job_id', 'jobid', 'trace_id', 'traceid', 'uuid', 'token']:
						if isinstance(value, (str, int)):
							ids.append(str(value))
					visit(value)
			elif isinstance(obj, list):
				for item in obj:
					visit(item)

		visit(payload)
		return list(dict.fromkeys(ids))

	def get_result_endpoint(self, sample_id, endpoint, submit_record):
		cached = self._load_cache(sample_id, endpoint)
		if cached:
			return cached

		param_names = ['job_id', 'id', 'trace_id', 'token']
		attempts = []
		for result_id in self._candidate_ids(submit_record):
			if result_id is None:
				response = self._request('GET', f'{self.base_url}/api/{endpoint}')
				attempts.append(self._response_record(response, {}))
				if 200 <= response.status_code < 300:
					self._save_cache(sample_id, endpoint, attempts[-1])
					return attempts[-1]
				continue
			for param_name in param_names:
				params = {param_name: result_id}
				response = self._request('GET', f'{self.base_url}/api/{endpoint}', params=params)
				attempts.append(self._response_record(response, params))
				if 200 <= response.status_code < 300:
					self._save_cache(sample_id, endpoint, attempts[-1])
					return attempts[-1]

		record = {'status_code': None, 'attempts': attempts}
		self._save_cache(sample_id, endpoint, record)
		return record

	def _response_record(self, response, params):
		record = {
			'status_code': response.status_code,
			'params': params,
			'text': response.text,
		}
		try:
			record['json'] = response.json()
		except ValueError:
			record['json'] = None
		return record

	def run_for_traceroute(self, sample_id, traceroute_text):
		submit = self.submit_traceroute(sample_id, traceroute_text)
		ip = self.get_result_endpoint(sample_id, 'ip', submit)
		lines = self.get_result_endpoint(sample_id, 'lines', submit)
		return {
			'submit': submit,
			'ip': ip,
			'lines': lines,
		}
