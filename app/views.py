from flask import Blueprint, redirect, render_template, request, url_for

from .auth import current_user, page_roles_required

bp = Blueprint("views", __name__)


@bp.app_context_processor
def template_identity():
    # An error page must still render when the identity query itself failed.
    if not request.environ.get("graduation.server_error"):
        current_user()
    return {"current_user": request.environ.get("graduation.public_user")}


@bp.get("/")
def index():
    user = current_user()
    if user is None:
        return redirect(url_for("views.login"))
    return redirect(url_for("views.admin" if user.role == "admin" else "views.entry"))


@bp.get("/login")
def login():
    if current_user() is not None:
        return redirect(url_for("views.index"))
    return render_template("login.html")


@bp.get("/admin")
@page_roles_required("admin")
def admin():
    return render_template("admin.html")


@bp.get("/entry")
@page_roles_required("staff", "admin")
def entry():
    return render_template("entry.html")


@bp.get("/stage")
@page_roles_required("staff", "admin")
def stage():
    return render_template("stage.html")


@bp.get("/display")
@page_roles_required("staff", "admin")
def display():
    return render_template("display.html")


@bp.get("/dashboard")
@page_roles_required("staff", "admin")
def dashboard():
    return render_template("dashboard.html")
