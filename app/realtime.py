from flask import current_app

from .auth import current_user
from .extensions import db, socketio
from .services.stage import stage_state
from .services.stats import compute_stats, invalidate_stats


@socketio.on("connect")
def on_connect(auth=None):
    return current_user() is not None


def _send(event, payload):
    try:
        socketio.emit(event, payload, namespace="/")
    except Exception:
        current_app.logger.exception("Could not emit %s after commit", event)


def broadcast(*events):
    """Publish committed transitions. QR tokens are absent from all public events."""
    actions = {event["action"] for event in events}
    try:
        invalidate_stats()
        for event in events:
            _send("participant_updated", event)
        if actions.intersection({"enqueue", "call", "complete"}):
            _send("stage_updated", stage_state())
        if actions.intersection({"create", "check_in", "enqueue", "call", "complete"}):
            _send("stats_updated", compute_stats())
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Could not publish committed participant changes")
