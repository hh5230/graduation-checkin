from flask import Blueprint

from ..auth import DISPLAY_ROLES, STAGE_ROLES, api_roles_required, current_user
from ..services import stage
from . import json_body, success

bp = Blueprint("stage_api", __name__, url_prefix="/api/stage")


@bp.post("/queue")
@api_roles_required(*STAGE_ROLES)
def queue():
    return success(stage.enqueue(json_body(allowed={"token", "code"}), current_user().id))


@bp.get("/state")
@api_roles_required(*DISPLAY_ROLES)
def state():
    return success(stage.stage_state())


@bp.post("/call-next")
@api_roles_required(*STAGE_ROLES)
def call_next():
    return success(stage.call_next(current_user().id, json_body(optional=True, allowed={"complete_current"})))


@bp.post("/complete")
@api_roles_required(*STAGE_ROLES)
def complete():
    return success(stage.complete(current_user().id, json_body(optional=True, allowed={"participant_id"})))


@bp.post("/requeue")
@api_roles_required(*STAGE_ROLES)
def requeue():
    return success(stage.requeue(current_user().id, json_body(allowed={"participant_id"})))
