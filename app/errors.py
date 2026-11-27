import re

from flask import current_app, jsonify, render_template, request
from sqlalchemy.exc import IntegrityError
from werkzeug.exceptions import HTTPException

from .extensions import db
from .i18n import get_lang, messages


class ApiError(Exception):
    def __init__(self, code, status, details=None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.details = details if details is not None else {}


def invalid_fields(**fields):
    return ApiError("VALIDATION_ERROR", 400, {"fields": fields})


def is_db_text(value):
    # JSON strings may contain NUL or unpaired surrogates, both invalid in PostgreSQL text.
    return isinstance(value, str) and re.search(r"[\x00\ud800-\udfff]", value) is None


def render_error(error):
    message = messages[error.code][get_lang()]
    if request.path == "/api" or request.path.startswith("/api/"):
        return jsonify(ok=False, error=dict(code=error.code, message=message, details=error.details)), error.status
    request.environ["graduation.server_error"] = error.status >= 500
    return render_template(
        "error.html", status_code=error.status, error_code=error.code, message=message,
    ), error.status


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def api_error(error):
        db.session.rollback()
        return render_error(error)

    @app.errorhandler(HTTPException)
    def http_error(error):
        db.session.rollback()
        codes = {400: "VALIDATION_ERROR", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
                 404: "NOT_FOUND", 405: "NOT_FOUND", 415: "UNSUPPORTED_MEDIA_TYPE"}
        response = app.make_response(render_error(ApiError(codes.get(error.code, "INTERNAL_ERROR"), error.code)))
        for header, value in error.get_headers():
            if header not in ("Content-Type", "Content-Length"):
                response.headers.add(header, value)
        return response

    @app.errorhandler(IntegrityError)
    def integrity_error(error):
        db.session.rollback()
        name = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if name == "participants_participant_code_key":
            return render_error(ApiError("DUPLICATE_CODE", 409, {"field": "participant_code"}))
        if name == "uq_participants_email_lower":
            return render_error(ApiError("DUPLICATE_EMAIL", 409, {"field": "email"}))
        if name == "uq_one_on_stage":
            from .services.stage import current_on_stage
            return render_error(ApiError("STAGE_BUSY", 409, {"current": current_on_stage()}))
        return unexpected_error(error)

    @app.errorhandler(Exception)
    def unexpected_error(error):
        db.session.rollback()
        current_app.logger.exception("Unhandled error on %s %s", request.method, request.path)
        return render_error(ApiError("INTERNAL_ERROR", 500))
