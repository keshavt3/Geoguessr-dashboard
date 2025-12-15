"""Web views for GeoGuessr Dashboard."""
import flask
import geodash


@geodash.app.route('/', methods=['GET'])
def index():
    """Display home page."""
    return flask.render_template('home.html')


@geodash.app.route('/about/', methods=['GET'])
def show_about():
    """Display about page."""
    return flask.render_template('about.html')


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
