from flask import Blueprint, request
from redis import Redis
from sqlalchemy import text

from ..auth import api_roles_required
from ..extensions import db, redis_operation
from ..errors import invalid_fields
from ..services.participants import positive_integer
from ..services.stats import get_stats, get_timeline
from . import success

bp = Blueprint("stats_api", __name__, url_prefix="/api")


@bp.get("/health")
def health():
    db.session.execute(text("SELECT 1")).scalar_one()
    return success({"db": "ok", "redis": "ok" if redis_operation(Redis.ping) else "error"})


@bp.get("/stats")
@api_roles_required("staff", "admin")
def stats():
    return success(get_stats())


@bp.get("/stats/timeline")
@api_roles_required("staff", "admin")
def timeline():
    minutes = positive_integer(request.args, "bucket_minutes", 30, maximum=120)
    if minutes < 5:
        raise invalid_fields(bucket_minutes="out_of_range")
    buckets = positive_integer(request.args, "buckets", 8, maximum=48)
    return success(get_timeline(minutes, buckets))
