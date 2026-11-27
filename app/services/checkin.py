from sqlalchemy import func

from ..errors import ApiError
from ..models import serialize_participant
from . import commit_changes, record_change
from .participants import transition_by_identifier


def check_in(data, operator_id):
    participant, changed = transition_by_identifier(
        data, "registered", status="checked_in", checked_in_at=func.now(), checked_in_by=operator_id,
    )
    if not changed:
        p = serialize_participant(participant)
        raise ApiError("ALREADY_CHECKED_IN", 409, {
            "checked_in_at": p["checked_in_at"], "checked_in_by": p["checked_in_by"], "participant": p,
        })
    event = record_change("check_in", participant, operator_id)
    commit_changes(event)
    return event["participant"]
