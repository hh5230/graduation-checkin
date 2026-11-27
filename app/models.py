from datetime import UTC, datetime

from flask import Flask
from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String,
    func, select, text,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.orm import Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash

from .config import ROOT
from .extensions import db


class User(db.Model):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('admin', 'staff')"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(16))
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def public_info(self):
        return {"id": self.id, "username": self.username,
                "display_name": self.display_name, "role": self.role}


class Participant(db.Model):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    participant_code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    email: Mapped[str] = mapped_column(String(255))
    qr_token: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), server_default=text("'registered'"))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_in_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    queued_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    called_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    called_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    checkin_operator: Mapped[User | None] = relationship(foreign_keys=[checked_in_by], lazy="joined")
    queue_operator: Mapped[User | None] = relationship(foreign_keys=[queued_by], lazy="joined")
    call_operator: Mapped[User | None] = relationship(foreign_keys=[called_by], lazy="joined")
    complete_operator: Mapped[User | None] = relationship(foreign_keys=[completed_by], lazy="joined")

    __table_args__ = (
        CheckConstraint("status IN ('registered','checked_in','queued','on_stage','completed')"),
        CheckConstraint("status = 'registered' OR checked_in_at IS NOT NULL", name="ck_checked_in_ts"),
        CheckConstraint("status NOT IN ('queued','on_stage','completed') OR queued_at IS NOT NULL", name="ck_queued_ts"),
        CheckConstraint("status NOT IN ('on_stage','completed') OR called_at IS NOT NULL", name="ck_called_ts"),
        CheckConstraint("status <> 'completed' OR completed_at IS NOT NULL", name="ck_completed_ts"),
        Index("uq_participants_email_lower", func.lower(email), unique=True),
        Index("uq_one_on_stage", text("(true)"), unique=True, postgresql_where=text("status = 'on_stage'")),
        Index("ix_participants_queue", queued_at, id, postgresql_where=text("status = 'queued'")),
        Index("ix_participants_status", status),
        Index("ix_participants_name_lower", func.lower(name)),
    )


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    participant_id: Mapped[int | None] = mapped_column(ForeignKey("participants.id", ondelete="SET NULL"))
    action: Mapped[str] = mapped_column(String(32))
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    details: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("action IN ('create','update','check_in','enqueue','call','complete','regenerate_qr')"),
        Index("ix_audit_logs_participant", participant_id, created_at),
    )


def serialize_participant(p: Participant, include_token=False):
    data = {field: getattr(p, field) for field in ("id", "participant_code", "name", "email", "status")}
    for field in ("checked_in_at", "queued_at", "called_at", "completed_at", "created_at", "updated_at"):
        timestamp = getattr(p, field)
        data[field] = timestamp.astimezone(UTC).isoformat() if timestamp else None
    for field, user in (("checked_in_by", p.checkin_operator), ("queued_by", p.queue_operator),
                        ("called_by", p.call_operator), ("completed_by", p.complete_operator)):
        data[field] = {"id": user.id, "name": user.display_name} if user else None
    if include_token:
        data["qr_token"] = p.qr_token
    return data


DEFAULT_USERS = (
    ("admin", "admin123", "admin", "Administrator"),
    ("staff1", "staff123", "staff", "Staff One"),
    ("staff2", "staff123", "staff", "Staff Two"),
)


def init_database(app: Flask):
    """Install the authoritative DDL and reconcile the three bootstrap accounts atomically."""
    with app.app_context(), db.session.begin():
        db.session.connection().exec_driver_sql((ROOT / "db/schema.sql").read_text(encoding="utf-8"))
        for username, password, role, display_name in DEFAULT_USERS:
            user = db.session.scalar(select(User).where(User.username == username))
            if user and check_password_hash(user.password_hash, password):
                if (user.role, user.display_name, user.is_active) == (role, display_name, True):
                    continue
                password_hash = user.password_hash
            else:
                password_hash = generate_password_hash(password)
            values = dict(password_hash=password_hash, role=role, display_name=display_name, is_active=True)
            statement = insert(User).values(username=username, **values)
            db.session.execute(statement.on_conflict_do_update(index_elements=[User.username], set_=values))
