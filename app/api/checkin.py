from flask import Blueprint, request

from ..auth import api_roles_required, current_user
from ..models import serialize_participant
from ..services.checkin import check_in
from ..services.participants import lookup
from . import json_body, success

bp = Blueprint("checkin_api", __name__, url_prefix="/api")


@bp.get("/lookup")
@api_roles_required("staff", "admin")
def lookup_participant():
    return success(serialize_participant(lookup(request.args)))


@bp.post("/checkin")
@api_roles_required("staff", "admin")
def checkin():
    return success(check_in(json_body(allowed={"token", "code"}), current_user().id))
