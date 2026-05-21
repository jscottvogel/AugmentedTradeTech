from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB
from apps.api.app.models.base import Base

class SyncQueue(Base):
    __tablename__ = "sync_queue"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    entity_type = Column(String, nullable=False) # job | job_note | job_photo | job_status | inspection_step
    entity_id = Column(String, nullable=False)
    operation = Column(String, nullable=False) # create | update | delete
    payload = Column(JSONB, nullable=False)
    client_timestamp = Column(DateTime(timezone=True), nullable=False)
    idempotency_key = Column(String, nullable=False, unique=True)
    status = Column(String, nullable=False, default="pending") # pending | processing | applied | conflict | failed
    conflict_detail = Column(JSONB, nullable=True)
    server_response = Column(JSONB, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    last_attempted_at = Column(DateTime(timezone=True), nullable=True)
    applied_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_sync_queue_company_id_user_id_status", "company_id", "user_id", "status"),
    )
