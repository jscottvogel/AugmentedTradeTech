from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.orm import DeclarativeBase, declared_attr

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models"""
    pass

class AuditMixin:
    """Mixin for tables requiring standard identity and audit trail columns"""
    @declared_attr
    def id(cls):
        return Column(String, primary_key=True)

    @declared_attr
    def created_at(cls):
        return Column(DateTime(timezone=True), nullable=False, server_default="now()")

    @declared_attr
    def updated_at(cls):
        return Column(DateTime(timezone=True), nullable=False, server_default="now()")

    @declared_attr
    def created_by(cls):
        return Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @declared_attr
    def updated_by(cls):
        return Column(String, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    @declared_attr
    def deleted_at(cls):
        return Column(DateTime(timezone=True), nullable=True)

class TenantAuditMixin(AuditMixin):
    """Mixin for tables requiring both standard audit trail and tenant scoping"""
    @declared_attr
    def company_id(cls):
        return Column(String, ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
