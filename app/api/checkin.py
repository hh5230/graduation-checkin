from flask import Blueprint, request

from ..auth import CHECKIN_ROLES, LOOKUP_ROLES, api_roles_required, current_user
from ..models import serialize_participant
from ..services.checkin import check_in
from ..services.participants import checkin_search, lookup
from . import json_body, success

bp = Blueprint("checkin_api", __name__, url_prefix="/api")


@bp.get("/lookup")
@api_roles_required(*LOOKUP_ROLES)
def lookup_participant():
    return success(serialize_participant(lookup(request.args)))


@bp.get("/checkin/search")
@api_roles_required(*CHECKIN_ROLES)
def search():
    return success(checkin_search(request.args.get("q", "")))


@bp.post("/checkin")
@api_roles_required(*CHECKIN_ROLES)
def checkin():
    return success(check_in(json_body(allowed={"token", "code", "entrance"}), current_user().id))
