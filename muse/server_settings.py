import os


MONGODB_URI = os.getenv('MUSE_MONGODB_URI', 'mongodb://127.0.0.1:27017')

MUSE_SERVER_HOST = os.getenv('MUSE_SERVER_HOST', '0.0.0.0')
MUSE_SERVER_PORT = int(os.getenv('MUSE_SERVER_PORT', 10813))

CACHE_DIR = os.getenv('MUSE_SERVER_CACHE_DIR', os.path.expanduser('~/.cache/muse_server'))
INPUT_ARCHIVE_DIR = os.path.join(CACHE_DIR, 'input_archive')
OUTPUT_ARCHIVE_DIR = os.path.join(CACHE_DIR, 'output_archive')
LOG_DIR = os.path.join(CACHE_DIR, 'log')
DEVICE_WORKSPACE = os.getenv('MUSE_DEVICE_WORKSPACE', '/data/local/tmp/muse')

for d in (INPUT_ARCHIVE_DIR, OUTPUT_ARCHIVE_DIR, LOG_DIR):
    os.makedirs(d, exist_ok=True)
