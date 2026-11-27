from flask import jsonify, request
from werkzeug.exceptions import BadRequest

from ..errors import ApiError, invalid_fields


def success(data, status=200):
    return jsonify(ok=True, data=data), status


def json_body(*, optional=False, allowed=None):
    if request.mimetype != "application/json":
        raise ApiError("UNSUPPORTED_MEDIA_TYPE", 415)
    if optional and not request.get_data():
        return {}
    try:
        body = request.get_json()
    except BadRequest:
        raise invalid_fields(body="invalid_json") from None
    if not isinstance(body, dict):
        raise invalid_fields(body="expected_object")
    if allowed is not None:
        unknown = body.keys() - allowed
        if unknown:
            raise invalid_fields(**{key: "unexpected" for key in unknown})
    return body
