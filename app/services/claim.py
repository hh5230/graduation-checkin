from base64 import b64encode

from flask import current_app
from sqlalchemy import func, select

from ..errors import ApiError, invalid_fields
from ..extensions import db, redis_operation
from ..models import Participant
from .participants import profile_values
from .qr import qr_png


def check_claim_rate(ip):
    key = f"ratelimit:claim:{ip}"

    def count_claim(redis):
        # Redis 7 EXPIRE NX sets the deadline only when the counter has no TTL.
        # MULTI/EXEC keeps every increment, deadline and TTL read together.
        with redis.pipeline(transaction=True) as pipe:
            pipe.incr(key)
            pipe.expire(key, current_app.config["CLAIM_RATE_WINDOW"], nx=True)
            pipe.ttl(key)
            return pipe.execute()

    result = redis_operation(count_claim)
    if result is not None:
        count, _, ttl = result
        if count > current_app.config["CLAIM_RATE_LIMIT"]:
            raise ApiError("RATE_LIMITED", 429, {"retry_after": ttl})


def claim_qr(body):
    # Supply both required keys so the registration validator reports all missing fields.
    values = profile_values({key: body.get(key) for key in ("participant_code", "email")}, partial=True)
    # JSON can represent unpaired UTF-16 surrogates that PostgreSQL text cannot store.
    try:
        values["email"].encode("utf-8")
    except UnicodeEncodeError:
        raise invalid_fields(email="invalid") from None
    stmt = select(Participant.participant_code, Participant.name, Participant.status, Participant.qr_token).where(
        func.upper(Participant.participant_code) == values["participant_code"],
        func.lower(Participant.email) == values["email"],
    )
    row = db.session.execute(stmt).one_or_none()
    if row is None:
        raise ApiError("CLAIM_NOT_FOUND", 404)
    png = qr_png(row.qr_token)
    current_app.logger.info("Participant QR claimed")
    return {
        "participant": {"participant_code": row.participant_code, "name": row.name, "status": row.status},
        "qr_png_base64": b64encode(png).decode("ascii"),
        "qr_filename": f"QR-{row.participant_code}.png",
    }
