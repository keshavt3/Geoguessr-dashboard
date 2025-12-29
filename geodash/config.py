"""GeoGuessr Dashboard configuration."""
import os
import pathlib

APPLICATION_ROOT = '/'
SECRET_KEY = os.environ.get('GEODASH_SECRET_KEY', 'dev-only-insecure-key').encode()
SESSION_COOKIE_NAME = 'geodash_session'

GEODASH_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATABASE_FILENAME = GEODASH_ROOT / 'var' / 'geodash.sqlite3'
