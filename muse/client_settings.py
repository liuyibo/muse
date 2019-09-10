import os

SERVER_URL = os.getenv('MUSE_SERVER_ADDRESS', 'http://127.0.0.1:10813/')

CACHE_DIR = os.getenv('MUSE_CACHE_DIR', os.path.expanduser('~/.cache/muse'))
INPUT_ARCHIVE_DIR = os.path.join(CACHE_DIR, 'input_archive')
OUTPUT_ARCHIVE_DIR = os.path.join(CACHE_DIR, 'output_archive')
EMPTY_FILENAME = '__empty.txt'
EMPTY_FILEPATH = os.path.join(CACHE_DIR, EMPTY_FILENAME)

for d in (INPUT_ARCHIVE_DIR, OUTPUT_ARCHIVE_DIR):
    os.makedirs(d, exist_ok=True)

with open(EMPTY_FILEPATH, 'w') as f:
    pass
