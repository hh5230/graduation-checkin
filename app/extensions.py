from flask import current_app
from flask_socketio import SocketIO
from flask_sqlalchemy import SQLAlchemy
from redis import Redis
from redis.exceptions import RedisError

db = SQLAlchemy()
socketio = SocketIO()


def get_redis() -> Redis:
    """Share a connection pool within this app. Opening a client does not connect."""
    if "redis" not in current_app.extensions:
        current_app.extensions["redis"] = Redis.from_url(
            current_app.config["REDIS_URL"], decode_responses=True,
            socket_connect_timeout=0.5, socket_timeout=0.5,
        )
    return current_app.extensions["redis"]


def redis_operation(operation):
    """A cache failure is a miss. A failed health probe also returns None."""
    try:
        return operation(get_redis())
    except (RedisError, OSError, ValueError) as exc:
        current_app.logger.warning("Redis %s failed: %s", operation.__name__, exc)
        return None
