import pickle
from collections import namedtuple

Cable = namedtuple('Cable', ['name', 'landing_points', 'length', 'owners', 'notes', 'rfs', 'other_info'])
LandingPoints = namedtuple('LandingPoints', ['latitude', 'longitude', 'country', 'location', 'cable'])


class NautilusUnpickler(pickle.Unpickler):
	def find_class(self, module, name):
		if module == '__main__' and name == 'Cable':
			return Cable
		if module == '__main__' and name == 'LandingPoints':
			return LandingPoints
		return super().find_class(module, name)


def load_pickle(file_obj):
	return NautilusUnpickler(file_obj).load()
