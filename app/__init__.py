from flask import Flask, jsonify, render_template
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import db


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from .routes.customers import bp as customers_bp
    from .routes.bills import bp as bills_bp
    from .routes.complaints import bp as complaints_bp
    from .routes.dashboard import bp as dashboard_bp

    app.register_blueprint(customers_bp, url_prefix="/api/customers")
    app.register_blueprint(bills_bp, url_prefix="/api/bills")
    app.register_blueprint(complaints_bp, url_prefix="/api/complaints")
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.errorhandler(HTTPException)
    def handle_http_error(err):
        return jsonify(error=err.name, message=err.description), err.code

    with app.app_context():
        db.create_all()

    return app
