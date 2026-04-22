"""SQLAlchemy ORM model definitions.

Define one class per database table using the DeclarativeBase pattern.
All models should live here (or be imported here) so Alembic can auto-generate
migrations from a single metadata object.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base — all models inherit from this.

    DeclarativeBase automatically creates and manages its own MetaData registry.
    Do not override Base.metadata — doing so severs the link between the base
    and its model registry, causing create_all() and Alembic autogenerate to
    silently miss all models.
    """


# REPLACE: define your ORM models below, for example:
#
# from sqlalchemy import String, Integer
# from sqlalchemy.orm import mapped_column, Mapped
#
# class ExampleRecord(Base):
#     __tablename__ = "example_records"
#
#     id: Mapped[int] = mapped_column(Integer, primary_key=True)
#     name: Mapped[str] = mapped_column(String(255), nullable=False)
