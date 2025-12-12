"""Web views for GeoGuessr Dashboard."""
import flask
import geodash


@geodash.app.route('/', methods=['GET'])
def index():
    """Redirect to stats page."""
    return flask.redirect(flask.url_for('show_stats'))


@geodash.app.route('/fetch/', methods=['GET'])
def show_fetch():
    """Display form to fetch new stats."""
    return flask.render_template('fetch.html')


@geodash.app.route('/stats/', methods=['GET'])
def show_stats():
    """Display stats page."""
    return flask.render_template('stats.html')


@geodash.app.route('/countries/<country_code>/', methods=['GET'])
def show_country(country_code):
    """Display stats for a specific country."""
    return flask.render_template('country.html', country_code=country_code)
