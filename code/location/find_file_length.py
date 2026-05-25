import pickle
import sys
from pathlib import Path
from collections import namedtuple
from utils.project_paths import log_path, output_path, raw_path, result_path

Location = namedtuple('Location', ['city', 'subdivisions', 'country', 'accuracy_radius', 'latitude', 'longitude', 'autonomous_system_number', 'network', 'ISP', 'Org'])

save_directory = output_path('location_data/iplocation_files')

if __name__ == '__main__':

    file_name = sys.argv[1]

    path = Path(save_directory / file_name)

    if path.is_file():

        with open(save_directory / file_name, 'rb') as f:
            d = pickle.load(f)

    else:
        d = {}

    print (len(d))

