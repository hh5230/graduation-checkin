from flask import Blueprint, request

from ..services.claim import check_claim_rate, claim_qr
from . import json_body, success

bp = Blueprint("public_api", __name__, url_prefix="/api/public")


@bp.post("/claim")
def claim():
    check_claim_rate(request.remote_addr)
    body = json_body(allowed={"participant_code", "email"})
    response, status = success(claim_qr(body))
    response.cache_control.no_store = True
    return response, status
