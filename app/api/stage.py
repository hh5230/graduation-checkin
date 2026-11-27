from flask import Blueprint

from ..auth import api_roles_required, current_user
from ..services import stage
from . import json_body, success

bp = Blueprint("stage_api", __name__, url_prefix="/api/stage")


@bp.post("/queue")
@api_roles_required("staff", "admin")
def queue():
    return success(stage.enqueue(json_body(allowed={"token", "code"}), current_user().id))


@bp.get("/state")
@api_roles_required("staff", "admin")
def state():
    return success(stage.stage_state())


@bp.post("/call-next")
@api_roles_required("staff", "admin")
def call_next():
    return success(stage.call_next(current_user().id, json_body(optional=True, allowed={"complete_current"})))


@bp.post("/complete")
@api_roles_required("staff", "admin")
def complete():
    return success(stage.complete(current_user().id, json_body(optional=True, allowed={"participant_id"})))
