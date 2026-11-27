from flask import Blueprint, session
from sqlalchemy import select
from werkzeug.security import check_password_hash

from ..auth import api_login_required, current_user
from ..errors import ApiError, invalid_fields
from ..extensions import db
from ..models import User
from . import json_body, success

bp = Blueprint("auth_api", __name__, url_prefix="/api/auth")


@bp.post("/login")
def login():
    data = json_body(allowed={"username", "password"})
    errors = {key: "required" for key in ("username", "password")
              if not isinstance(data.get(key), str) or not data[key]}
    if errors:
        raise invalid_fields(**errors)
    username = data["username"]
    user = db.session.scalar(select(User).where(User.username == username)) if "\x00" not in username else None
    if not user or not user.is_active or not check_password_hash(user.password_hash, data["password"]):
        raise ApiError("INVALID_CREDENTIALS", 401)
    session.clear()
    session["user_id"] = user.id
    return success({"user": user.public_info()})


@bp.post("/logout")
@api_login_required
def logout():
    json_body(optional=True, allowed=set())
    session.clear()
    return success({})


@bp.get("/me")
@api_login_required
def me():
    return success({"user": current_user().public_info()})
