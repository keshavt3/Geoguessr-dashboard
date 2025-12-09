"""GeoGuessr Dashboard database connection."""
import sqlite3
import flask
import geodash


def dict_factory(cursor, row):
    """Convert database row to dictionary."""
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def get_db():
    """Open a new database connection."""
    if 'sqlite_db' not in flask.g:
        db_path = geodash.app.config['DATABASE_FILENAME']
        flask.g.sqlite_db = sqlite3.connect(str(db_path))
        flask.g.sqlite_db.row_factory = dict_factory
        # Enable foreign keys
        flask.g.sqlite_db.execute("PRAGMA foreign_keys = ON")
    return flask.g.sqlite_db


def close_db(error):
    """Close the database connection."""
    db = flask.g.pop('sqlite_db', None)
    if db is not None:
        db.commit()
        db.close()
