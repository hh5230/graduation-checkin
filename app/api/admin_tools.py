from datetime import UTC, datetime

from flask import Blueprint, Response, request, stream_with_context

from ..auth import ADMIN_ROLES, api_roles_required, current_user
from ..errors import invalid_fields
from ..services import admin_tools
from . import json_body, success

bp = Blueprint("admin_tools_api", __name__, url_prefix="/api")


@bp.post("/participants/import")
@api_roles_required(*ADMIN_ROLES)
def import_csv():
    if request.mimetype != "multipart/form-data":
        raise invalid_fields(file="expected_multipart")
    file = request.files.get("file")
    if file is None:
        raise invalid_fields(file="required")
    return success(admin_tools.import_participants(file.stream, current_user().id))


@bp.get("/participants/<int:participant_id>/timeline")
@api_roles_required(*ADMIN_ROLES)
def timeline(participant_id):
    return success(admin_tools.participant_timeline(participant_id))


@bp.post("/participants/<int:participant_id>/undo")
@api_roles_required(*ADMIN_ROLES)
def undo(participant_id):
    body = json_body(allowed={"reason"})
    return success(admin_tools.undo(participant_id, body.get("reason"), current_user().id))


@bp.get("/export/records.csv")
@api_roles_required(*ADMIN_ROLES)
def export_records():
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(stream_with_context(admin_tools.records_csv()), mimetype="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="graduation-records-{stamp}.csv"',
                             "Cache-Control": "no-store"})
