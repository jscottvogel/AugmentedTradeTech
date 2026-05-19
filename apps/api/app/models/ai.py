from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.dialects.postgresql import JSONB, INET
from pgvector.sqlalchemy import Vector
from apps.api.app.models.base import Base

class AIRequest(Base):
    __tablename__ = "ai_requests"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    user_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    request_type = Column(String, nullable=False) # nameplate_scan | fault_analysis | diagnosis | readings_analysis | tech_chat | auto_document
    model = Column(String, nullable=False)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    cost_usd_micro = Column(Integer, nullable=True)
    feature_tag = Column(String, nullable=False)
    cache_hit = Column(Boolean, nullable=False, default=False)
    latency_ms = Column(Integer, nullable=True)
    status = Column(String, nullable=False) # success | error | timeout
    error_detail = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

class JobEmbedding(Base):
    __tablename__ = "job_embeddings"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    job_id = Column(String, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, unique=True)
    embedding = Column(Vector(1536), nullable=False) # Claude / OpenAI embedding dimensions
    embed_text = Column(String, nullable=False)
    model_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")

    __table_args__ = (
        Index(
            "idx_job_embeddings_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"}
        ),
    )

class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(String, primary_key=True)
    company_id = Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=True)
    actor_id = Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_role = Column(String, nullable=False)
    action = Column(String, nullable=False) # e.g. job.status_changed | invoice.paid
    entity_type = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    before_state = Column(JSONB, nullable=True)
    after_state = Column(JSONB, nullable=True)
    ip_address = Column(INET, nullable=True)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default="now()")
