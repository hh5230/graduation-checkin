from ..extensions import db
from ..models import AuditLog, serialize_participant


def record_change(action, participant, operator_id, details=None):
    """Stage the audit insert and freeze the public event while we still hold the row lock."""
    db.session.add(AuditLog(
        action=action, participant_id=participant.id, operator_id=operator_id,
        details=details or {},
    ))
    return {"action": action, "participant": serialize_participant(participant)}


def commit_changes(*events, stats_changed=False):
    from ..realtime import broadcast

    db.session.commit()
    broadcast(*events, stats_changed=stats_changed)
