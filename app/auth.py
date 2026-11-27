from functools import wraps
from urllib.parse import urlencode

from flask import redirect, request, session, url_for

from .errors import ApiError
from .extensions import db
from .models import User


def current_user():
    if "graduation.user" not in request.environ:
        user_id = session.get("user_id")
        user = db.session.get(User, user_id, populate_existing=True) if isinstance(user_id, int) else None
        active_user = user if user and user.is_active else None
        request.environ["graduation.user"] = active_user
        request.environ["graduation.public_user"] = active_user.public_info() if active_user else None
    return request.environ["graduation.user"]


def api_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            raise ApiError("UNAUTHORIZED", 401)
        return view(*args, **kwargs)
    return wrapped


def page_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if current_user() is None:
            target = request.full_path if request.query_string else request.path
            return redirect(url_for("views.login") + "?" + urlencode({"next": target}, safe="/"))
        return view(*args, **kwargs)
    return wrapped


def _roles_required(login_required, roles):
    def decorate(view):
        @login_required
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user().role not in roles:
                raise ApiError("FORBIDDEN", 403)
            return view(*args, **kwargs)
        return wrapped
    return decorate


def api_roles_required(*roles):
    return _roles_required(api_login_required, roles)


def page_roles_required(*roles):
    return _roles_required(page_login_required, roles)
