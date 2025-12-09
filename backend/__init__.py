from flask import Flask, send_from_directory
from flask_cors import CORS
from backend.routes.stats import stats_bp

def create_app():
    app = Flask(__name__)
    CORS(app, supports_credentials=True)
    app.register_blueprint(stats_bp)

    @app.route('/')
    def serve_test():
        return send_from_directory('..', 'test.html')

    return app
