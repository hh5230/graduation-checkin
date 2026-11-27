import argparse
import sys
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import Participant
from app.services.participants import new_token
from app.services.stats import invalidate_stats

NAMES = (
    "林雨桐", "Daniel Chen", "王亦辰", "Amelia Wong", "赵子涵", "Ethan Miller",
    "刘思远", "Sofia Patel", "陈星宇", "Oliver Lee", "何嘉欣", "Grace Taylor",
    "徐书航", "Noah Davis", "杨可心", "Chloe Kim", "周明轩", "Lucas Garcia",
    "梁芷晴", "Isabel Tan", "许知行", "Benjamin Scott", "郑安琪", "Maya Singh",
    "郭景然", "Theo Martin", "沈若宁", "Emma Wilson", "吴泽宇", "Alice Zhang",
)


def main():
    parser = argparse.ArgumentParser(description="Seed the 30 graduation participants.")
    parser.add_argument("--reset", action="store_true", help="truncate participants and audit logs first")
    args = parser.parse_args()
    with create_app().app_context():
        with db.session.begin():
            if args.reset:
                db.session.execute(text("TRUNCATE participants, audit_logs RESTART IDENTITY CASCADE"))
            codes = [f"G2026{i:03d}" for i in range(1, len(NAMES) + 1)]
            existing = set(db.session.scalars(select(Participant.participant_code).where(
                Participant.participant_code.in_(codes))))
            rows = [
                dict(participant_code=code, name=name, email=f"student{i:03d}@example.edu", qr_token=new_token())
                for i, (code, name) in enumerate(zip(codes, NAMES), 1) if code not in existing
            ]
            inserted = 0
            if rows:
                stmt = insert(Participant).values(rows).on_conflict_do_nothing(index_elements=["participant_code"])
                inserted = len(db.session.scalars(stmt.returning(Participant.id)).all())
        invalidate_stats()
        print(f"Seeded {len(NAMES)} participants: {inserted} inserted, {len(NAMES) - inserted} already present.")


if __name__ == "__main__":
    main()
