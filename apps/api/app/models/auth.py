import ulid
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from apps.api.app.models.base import Base, AuditMixin

def generate_ulid_string():
    return str(ulid.new())

class MagicLinkToken(Base, AuditMixin):
    __tablename__ = "magic_link_tokens"

    id = Column(String, primary_key=True, default=generate_ulid_string)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship to User
    user = relationship("User", foreign_keys=[user_id])

class RefreshToken(Base, AuditMixin):
    __tablename__ = "refresh_tokens"

    id = Column(String, primary_key=True, default=generate_ulid_string)
    user_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Relationship to User
    user = relationship("User", foreign_keys=[user_id])

class CustomerMagicLinkToken(Base, AuditMixin):
    __tablename__ = "customer_magic_link_tokens"

    id = Column(String, primary_key=True, default=generate_ulid_string)
    customer_id = Column(String, ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationship to Customer
    customer = relationship("Customer", foreign_keys=[customer_id])
