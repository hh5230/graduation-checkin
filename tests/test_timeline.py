from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app.extensions import db
from app.services.stats import get_timeline
from tests import check_in, error, success


PATH = "/api/stats/timeline"


def test_timeline_access_and_defaults(client, staff_client, admin_client):
    error(client.get(PATH), 401, "UNAUTHORIZED")
    for authorized in (staff_client, admin_client):
        data = success(authorized.get(PATH))
        assert data["bucket_minutes"] == 30
        buckets = data["buckets"]
        assert len(buckets) == 8
        assert [b["current"] for b in buckets] == [False] * 7 + [True]
        assert all(b["count"] == 0 for b in buckets)
        for i, bucket in enumerate(buckets):
            start, end = (datetime.fromisoformat(bucket[k]) for k in ("start", "end"))
            assert start.utcoffset() == end.utcoffset() == timedelta(0)
            assert end - start == timedelta(minutes=30)
            if i:
                assert buckets[i - 1]["end"] == bucket["start"]


@pytest.mark.parametrize("query", ["bucket_minutes=4", "bucket_minutes=121", "bucket_minutes=",
                                   "buckets=0", "buckets=49", "buckets=-1", "buckets=1.5", "buckets=x"])
def test_timeline_rejects_invalid_parameters(staff_client, query):
    error(staff_client.get(f"{PATH}?{query}"), 400, "VALIDATION_ERROR")


def test_timeline_counts_and_edges(app, staff_client, make_participant):
    people = [make_participant() for _ in range(5)]
    for person in people:
        check_in(staff_client, person)
    single = success(staff_client.get(f"{PATH}?bucket_minutes=120&buckets=1"))["buckets"]
    assert len(single) == 1 and single[0]["count"] == 5 and single[0]["current"]
    # PostgreSQL now() is stable throughout this transaction, including the service read.
    with app.app_context(), db.session.begin():
        for person, minutes_ago in zip(people, [16, 15, 10, 1, 0], strict=True):
            db.session.execute(text("""
                UPDATE participants SET checked_in_at = now() - make_interval(mins => :age)
                WHERE id = :id
            """), {"age": minutes_ago, "id": person["id"]})
        assert [b["count"] for b in get_timeline(5, 3)["buckets"]] == [1, 1, 1]

    buckets = success(staff_client.get(f"{PATH}?bucket_minutes=5&buckets=3"))["buckets"]
    assert [b["count"] for b in buckets] == [1, 0, 2]
