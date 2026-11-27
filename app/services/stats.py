import json

from flask import current_app
from redis.exceptions import WatchError
from sqlalchemy import text

from ..extensions import db, redis_operation

CACHE_KEY = "stats:v1"
COUNTS = text("""
    SELECT count(*) AS total,
           count(*) FILTER (WHERE status <> 'registered') AS checked_in,
           count(*) FILTER (WHERE status = 'registered') AS not_checked_in,
           count(*) FILTER (WHERE status = 'queued') AS waiting,
           count(*) FILTER (WHERE status = 'on_stage') AS on_stage,
           count(*) FILTER (WHERE status = 'completed') AS completed
    FROM participants
""")


def compute_stats():
    return dict(db.session.execute(COUNTS).mappings().one())


def _delete_stats(client):
    with client.pipeline() as pipe:
        # DEL alone on an absent key would not notify a concurrent WATCH.
        # Both commands run in one EXEC, so readers never see the placeholder.
        pipe.set(CACHE_KEY, "", nx=True).delete(CACHE_KEY).execute()


def invalidate_stats():
    redis_operation(_delete_stats)


def _cached_stats(client):
    cached = client.get(CACHE_KEY)
    if cached is not None:
        try:
            return json.loads(cached)
        except (ValueError, TypeError):
            current_app.logger.warning("Ignoring unreadable stats cache")
    with client.pipeline() as pipe:
        pipe.watch(CACHE_KEY)
        stats = compute_stats()
        pipe.multi()
        pipe.setex(CACHE_KEY, current_app.config["STATS_CACHE_TTL"], json.dumps(stats))
        try:
            pipe.execute()
        except WatchError:
            # Another fill or a committed change won the race. Discard this cache write.
            pass
        return stats


def get_stats():
    if current_app.config["STATS_CACHE_TTL"] > 0:
        stats = redis_operation(_cached_stats)
        if stats is not None:
            return stats
    return compute_stats()
