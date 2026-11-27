from flask import Blueprint, Response, request

from ..auth import api_roles_required, current_user
from ..models import serialize_participant
from ..services import participants
from ..services.qr import qr_png
from . import json_body, success

bp = Blueprint("participants_api", __name__, url_prefix="/api/participants")


@bp.get("")
@api_roles_required("admin")
def listing():
    return success(participants.list_participants(request.args))


@bp.post("")
@api_roles_required("admin")
def create():
    return success(participants.create_participant(json_body(), current_user().id), 201)


@bp.get("/<int:participant_id>")
@api_roles_required("admin")
def detail(participant_id):
    return success(serialize_participant(participants.get_participant(participant_id), include_token=True))


@bp.patch("/<int:participant_id>")
@api_roles_required("admin")
def update(participant_id):
    return success(participants.update_participant(participant_id, json_body(), current_user().id))


@bp.post("/<int:participant_id>/regenerate-qr")
@api_roles_required("admin")
def regenerate_qr(participant_id):
    json_body(optional=True, allowed=set())
    return success(participants.regenerate_qr(participant_id, current_user().id))


@bp.get("/<int:participant_id>/qr.png")
@api_roles_required("admin")
def png(participant_id):
    token = participants.get_participant(participant_id).qr_token
    return Response(qr_png(token), mimetype="image/png", headers={"Cache-Control": "no-store"})
