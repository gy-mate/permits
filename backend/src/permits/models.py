"""Declarative ORM model for the ``permits.permits`` table."""

import datetime as dt

from geoalchemy2 import Geometry
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
)
from sqlalchemy import (
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from permits.usage_types import UsageType

SCHEMA = "permits"
LOCAL_SCHEMA = "local"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


class HU(Base):
    """A Hungarian settlement, keyed by its Wikidata id and holding its KSH code."""

    __tablename__ = "hu"
    __table_args__ = (
        UniqueConstraint("city_wikidata_id", name="uq_hu_city_wikidata_id"),
        {"schema": LOCAL_SCHEMA},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    city_wikidata_id: Mapped[str] = mapped_column(Text, nullable=False)
    ksh_code: Mapped[str] = mapped_column(Text, nullable=False)
    local_authority_id: Mapped[str] = mapped_column(Text, nullable=False)


class Permit(Base):
    """A single public-space-use permit, enriched with geometry + identity."""

    __tablename__ = "permits"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    queried_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    city_wikidata_id: Mapped[str] = mapped_column(
        ForeignKey(f"{LOCAL_SCHEMA}.hu.city_wikidata_id", name="fk_permits_city_wikidata_id"),
        nullable=False,
    )
    hu: Mapped[HU] = relationship(lazy="joined")

    department_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    main_registration_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sub_registration_number: Mapped[int] = mapped_column(Integer, nullable=False)
    year_number: Mapped[int] = mapped_column(Integer, nullable=False)

    client_is_natural_person: Mapped[bool] = mapped_column(Boolean, nullable=False)
    client: Mapped[str | None] = mapped_column(Text, nullable=True)
    client_wikidata_id: Mapped[str | None] = mapped_column(Text, nullable=True)

    location_source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_conscription_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
        nullable=True,
    )

    usage_type: Mapped[UsageType] = mapped_column(
        SAEnum(UsageType, name="usage_type", schema=SCHEMA, values_callable=lambda e: [m.value for m in e]),
        nullable=False,
    )
    occupied_area_in_square_metres: Mapped[int | None] = mapped_column(Integer, nullable=True)

    time_from: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    time_to: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
