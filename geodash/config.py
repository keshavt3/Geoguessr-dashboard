"""GeoGuessr Dashboard configuration."""
import pathlib

APPLICATION_ROOT = '/'
SECRET_KEY = b'\x1a\x2b\x3c\x4d\x5e\x6f\x7a\x8b\x9c\xad\xbe\xcf\xda\xeb\xfc\x0d'
SESSION_COOKIE_NAME = 'geodash_session'

GEODASH_ROOT = pathlib.Path(__file__).resolve().parent.parent
DATABASE_FILENAME = GEODASH_ROOT / 'var' / 'geodash.sqlite3'
