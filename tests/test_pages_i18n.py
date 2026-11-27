import json
from urllib.parse import parse_qs, urlsplit

import pytest


ERROR_CODES = {
    "UNAUTHORIZED", "INVALID_CREDENTIALS", "FORBIDDEN", "VALIDATION_ERROR", "UNSUPPORTED_MEDIA_TYPE",
    "NOT_FOUND", "PARTICIPANT_NOT_FOUND", "INVALID_QR", "DUPLICATE_CODE", "DUPLICATE_EMAIL",
    "ALREADY_CHECKED_IN", "NOT_CHECKED_IN", "ALREADY_QUEUED", "INVALID_STATE", "QUEUE_EMPTY",
    "STAGE_BUSY", "NOTHING_ON_STAGE", "INTERNAL_ERROR",
}


def test_login_and_anonymous_redirect(client):
    page = client.get("/login")
    assert page.status_code == 200 and page.mimetype == "text/html"
    response = client.get("/admin")
    assert response.status_code == 302
    location = urlsplit(response.headers["Location"])
    assert location.path == "/login"
    assert parse_qs(location.query)["next"] == ["/admin"]


@pytest.mark.parametrize("path,status", [
    ("/admin", 403), ("/entry", 200), ("/stage", 200), ("/display", 200), ("/dashboard", 200),
])
def test_staff_pages(staff_client, path, status):
    response = staff_client.get(path)
    assert response.status_code == status
    assert response.mimetype == "text/html"


def test_admin_page(admin_client):
    result = admin_client.get("/admin")
    assert result.status_code == 200 and result.mimetype == "text/html"


def test_served_locales_cover_contract_errors(client):
    def translations(language):
        response = client.get(f"/static/i18n/{language}.json")
        assert response.status_code == 200
        return json.loads(response.data)

    zh, en = translations("zh"), translations("en")
    assert zh.keys() == en.keys()
    for code in ERROR_CODES:
        key = f"error.{code}"
        assert zh[key].strip() and en[key].strip()
