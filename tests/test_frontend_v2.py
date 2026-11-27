"""Render the operator pages through their real Flask routes and signed-in sessions."""
import json
from html.parser import HTMLParser
from urllib.parse import urlsplit

import pytest
from werkzeug.security import generate_password_hash

from app.extensions import db
from app.models import User


PAGES = ("/admin", "/entry", "/stage", "/display", "/dashboard")
ACCOUNTS = [
    ("admin", "admin123", "admin", PAGES),
    ("staff1", "staff123", "staff", ("/entry", "/stage", "/display", "/dashboard")),
    ("checkin1", "checkin123", "checkin", ("/entry", "/dashboard")),
    ("stage1", "stage123", "stage", ("/stage", "/display", "/dashboard")),
    ("viewer1", "viewer123", "viewer", ("/dashboard", "/display")),
]


class Page(HTMLParser):
    def __init__(self, response):
        super().__init__()
        self.navs = {}
        self.nav = None
        self.ids = {}
        self.links = []
        self.tags = []
        self.stat_cards = 0
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        if "id" in attrs:
            self.ids[attrs["id"]] = attrs
        if tag == "nav":
            self.nav = attrs["class"]
            self.navs[self.nav] = []
        if tag == "a" and "href" in attrs:
            path = urlsplit(attrs["href"]).path
            self.links.append(path)
            if self.nav:
                self.navs[self.nav].append(path)
        if "stat-card" in attrs.get("class", "").split():
            self.stat_cards += 1

    def handle_endtag(self, tag):
        if tag == "nav":
            self.nav = None


@pytest.fixture(scope="module")
def operator_accounts(app):
    with app.app_context():
        for username, password, role, _ in ACCOUNTS:
            if db.session.scalar(db.select(User).where(User.username == username)) is None:
                db.session.add(User(username=username, password_hash=generate_password_hash(password),
                                    display_name=username, role=role, is_active=True))
        db.session.commit()


@pytest.mark.parametrize("username,password,role,allowed", ACCOUNTS, ids=[r[2] for r in ACCOUNTS])
def test_rendered_role_workspaces(operator_accounts, client, username, password, role, allowed):
    assert client.post("/api/auth/login", json={"username": username, "password": password}).status_code == 200
    for path in PAGES:
        response = client.get(path)
        assert response.status_code == (200 if path in allowed else 403), (role, path)
        page = Page(response)
        assert not (set(page.links) & (set(PAGES) - set(allowed))), (role, path)
        if path == "/display" and path in allowed:
            assert not page.navs and "hidden" in page.ids["display-back"]
            assert {"display-name", "display-next", "conn-status"} <= page.ids.keys()
            continue
        for nav in ("side-nav", "bottom-nav"):
            assert page.navs[nav] == list(allowed), (role, path, nav)
        if "/entry" in allowed:
            assert page.ids["global-search"]["action"] == ("/admin" if role == "admin" else "/entry")
        else:
            assert "global-search" not in page.ids and "search-toggle" not in page.ids
        if path not in allowed:
            continue
        if path == "/entry":
            assert {"entrance-dialog", "entry-search", "confirm-checkin", "scan-photo", "result-overlay"} <= page.ids.keys()
        if path == "/stage":
            assert {"stage-next", "stage-length", "requeue-sheet", "call-next", "complete", "result-overlay"} <= page.ids.keys()
        if path == "/dashboard":
            assert page.stat_cards == 6
            assert {"checkin-rate", "timeline"} <= page.ids.keys()
            assert ("dash-current" in page.ids) == ("/display" in allowed)
        if path == "/admin":
            assert {"print-sheet", "import-form", "audit-list", "undo-form"} <= page.ids.keys()
            assert "/api/export/records.csv" in page.links
    assert client.get("/admin/qr-sheet").status_code == (200 if role == "admin" else 403)
    assert client.get("/claim").status_code == 200


def test_frontend_v2_locales(client):
    zh, en = [json.loads(client.get(f"/static/i18n/{lang}.json").data) for lang in ("zh", "en")]
    assert zh.keys() == en.keys()
    keys = {"feedback.colleague", "display.idle", "entry.entrance", "stage.requeue", "admin.undo"}
    keys.update(f"role.{role}" for _, _, role, _ in ACCOUNTS)
    keys.update(f"action.{action}" for action in (
        "create", "update", "check_in", "enqueue", "call", "complete", "regenerate_qr", "requeue", "undo", "import",
    ))
    assert all(zh[key].strip() and en[key].strip() for key in keys)
