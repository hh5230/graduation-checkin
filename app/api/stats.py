from flask import Blueprint
from redis import Redis
from sqlalchemy import text

from ..auth import api_roles_required
from ..extensions import db, redis_operation
from ..services.stats import get_stats
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
