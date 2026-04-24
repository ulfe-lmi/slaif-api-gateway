"""Database primitives for SQLAlchemy-based persistence."""

from slaif_gateway.db.base import Base, metadata, naming_convention

__all__ = ["Base", "metadata", "naming_convention"]
