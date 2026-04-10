import uuid
from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Boolean,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, DeclarativeBase
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Severity(str, PyEnum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


class IncidentStatus(str, PyEnum):
    RECEIVED = "received"
    TRIAGING = "triaging"
    TRIAGED = "triaged"
    TICKET_CREATED = "ticket_created"
    NOTIFIED = "notified"
    RESOLVED = "resolved"
    FAILED = "failed"


class TeamName(str, PyEnum):
    BACKEND = "backend"
    FRONTEND = "frontend"
    PAYMENTS = "payments"
    INFRASTRUCTURE = "infrastructure"
    DATABASE = "database"
    UNKNOWN = "unknown"


class Incident(Base):
    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    reporter_email = Column(String(255), nullable=False)
    reporter_name = Column(String(255), nullable=False)
    severity_hint = Column(Enum(Severity), nullable=True)
    status = Column(
        Enum(IncidentStatus),
        nullable=False,
        default=IncidentStatus.RECEIVED,
    )
    assigned_team = Column(Enum(TeamName), nullable=True)
    triage_summary = Column(Text, nullable=True)
    affected_components = Column(JSON, nullable=True)
    root_cause_hint = Column(Text, nullable=True)
    severity_final = Column(Enum(Severity), nullable=True)
    linear_ticket_id = Column(String(100), nullable=True)
    linear_ticket_url = Column(String(500), nullable=True)
    slack_message_ts = Column(String(100), nullable=True)
    attachments = Column(JSON, nullable=True)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    audit_logs = relationship("AuditLog", back_populates="incident", cascade="all, delete-orphan")


class AuditLog(Base):
    __tablename__ = "incident_audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    stage = Column(String(100), nullable=False)
    message = Column(Text, nullable=False)
    extra_data = Column(JSON, nullable=True)
    success = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="audit_logs")
