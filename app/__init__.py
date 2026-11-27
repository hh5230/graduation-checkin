import logging
import sys

from flask import Flask
from socketio import Manager
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config, TestConfig
from .extensions import db, socketio
from .models import init_database


def create_app(config_name: str | None = None):
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    app = Flask(__name__)
    app.config.from_object(TestConfig() if config_name == "testing" else Config())
    db.init_app(app)

    from . import realtime, views
    from .api import admin_tools, auth, checkin, participants, public, stage, stats
    from .errors import register_error_handlers

    for blueprint in (auth.bp, participants.bp, checkin.bp, public.bp, stage.bp, stats.bp, views.bp):
        app.register_blueprint(blueprint)
    app.register_blueprint(admin_tools.bp)
    register_error_handlers(app)

    # The in-process test client needs a local Manager even after a production factory call.
    if app.testing:
        options = {"message_queue": None, "client_manager": Manager()}
    else:
        options = {"message_queue": app.config["REDIS_URL"]}
    proxy = None
    if app.config["TRUST_PROXY"]:
        hops = app.config["PROXY_HOPS"]
        proxy = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)
        app.wsgi_app = proxy
    socketio.init_app(app, async_mode=app.config["SOCKETIO_ASYNC_MODE"], cors_allowed_origins=None, **options)
    if proxy is not None:
        # init_app puts its dispatcher ahead of the Flask fallback. Move it
        # inside ProxyFix so polling and WebSocket requests see the same environ.
        dispatcher = app.wsgi_app
        dispatcher.wsgi_app = proxy.app
        proxy.app = dispatcher
        app.wsgi_app = proxy

    @app.cli.command("init-db")
    def init_db_command():
        init_database(app)
        print("Database initialized.")

    return app
