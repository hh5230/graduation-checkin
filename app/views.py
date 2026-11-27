from pathlib import Path

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_file, url_for

from .auth import ADMIN_ROLES, CHECKIN_ROLES, DISPLAY_ROLES, STAGE_ROLES, VIEW_ROLES, current_user, page_roles_required
from .i18n import get_lang
from .services.participants import qr_sheet_participants

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
    return redirect(user.home)


@bp.get("/login")
def login():
    user = current_user()
    if user is not None:
        return redirect(user.home)
    return render_template("login.html")


@bp.get("/claim")
def claim():
    return render_template("claim.html")


@bp.get("/ca.crt")
def ca_certificate():
    path = current_app.config["CA_CERT_PATH"]
    if not path or not Path(path).is_file():
        abort(404)
    response = send_file(Path(path).resolve(), mimetype="application/x-x509-ca-cert",
                         as_attachment=True, download_name="graduation-ca.crt")
    response.headers["Content-Disposition"] = 'attachment; filename="graduation-ca.crt"'
    return response


@bp.get("/admin")
@page_roles_required(*ADMIN_ROLES)
def admin():
    return render_template("admin.html")


@bp.get("/admin/qr-sheet")
@page_roles_required(*ADMIN_ROLES)
def qr_sheet():
    return render_template("qr_sheet.html", participants=qr_sheet_participants(request.args), lang=get_lang())


@bp.get("/entry")
@page_roles_required(*CHECKIN_ROLES)
def entry():
    return render_template("entry.html")


@bp.get("/stage")
@page_roles_required(*STAGE_ROLES)
def stage():
    return render_template("stage.html")


@bp.get("/display")
@page_roles_required(*DISPLAY_ROLES)
def display():
    return render_template("display.html")


@bp.get("/dashboard")
@page_roles_required(*VIEW_ROLES)
def dashboard():
    return render_template("dashboard.html")
