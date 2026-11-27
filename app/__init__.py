import logging
import sys

from flask import Flask
from socketio import Manager

from .config import Config, TestConfig
from .extensions import db, socketio
from .models import init_database


def create_app(config_name: str | None = None):
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    app = Flask(__name__)
    app.config.from_object(TestConfig() if config_name == "testing" else Config())
    db.init_app(app)

    from . import realtime, views
    from .api import auth, checkin, participants, stage, stats
    from .errors import register_error_handlers

    for blueprint in (auth.bp, participants.bp, checkin.bp, stage.bp, stats.bp, views.bp):
        app.register_blueprint(blueprint)
    register_error_handlers(app)

    # The in-process test client needs a local Manager even after a production factory call.
    if app.testing:
        socketio.init_app(app, message_queue=None, client_manager=Manager(),
                          async_mode="threading", cors_allowed_origins=None)
    else:
        socketio.init_app(app, message_queue=app.config["REDIS_URL"],
                          async_mode="threading", cors_allowed_origins=None)

    @app.cli.command("init-db")
    def init_db_command():
        init_database(app)
        print("Database initialized.")

    return app
