"""GeoGuessr Dashboard package initializer."""
import flask

app = flask.Flask(__name__)

app.config.from_object('geodash.config')

app.config.from_envvar('GEODASH_SETTINGS', silent=True)

import geodash.model  # noqa: E402
import geodash.views.index  # noqa: E402
import geodash.api.stats  # noqa: E402

app.teardown_appcontext(geodash.model.close_db)
