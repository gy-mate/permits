"""Initial schema: PostGIS, permits schema, usage_type enum, permits table.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-27
"""

import geoalchemy2
import sqlalchemy as sa
from alembic import op

from permits.usage_types import UsageType

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA = "permits"
ENUM_VALUES = [member.value for member in UsageType]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "permits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("queried_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("city_wikidata_id", sa.Text(), nullable=False),
        sa.Column("city_ksh_code", sa.Text(), nullable=False),
        sa.Column("reference_number", sa.Text(), nullable=False),
        sa.Column("client_is_natural_person", sa.Boolean(), nullable=False),
        sa.Column("client", sa.Text(), nullable=True),
        sa.Column("client_wikidata_id", sa.Text(), nullable=True),
        sa.Column("location_source_text", sa.Text(), nullable=True),
        sa.Column("location_conscription_number", sa.Text(), nullable=True),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="GEOMETRY", srid=4326, spatial_index=False),
            nullable=True,
        ),
        sa.Column(
            "usage_type",
            sa.Enum(*ENUM_VALUES, name="usage_type", schema=SCHEMA),
            nullable=False,
        ),
        sa.Column("occupied_area_in_square_metres", sa.Integer(), nullable=True),
        sa.Column("time_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("time_to", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("reference_number", name="uq_permits_reference_number"),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_permits_location",
        "permits",
        ["location"],
        schema=SCHEMA,
        postgresql_using="gist",
    )


def downgrade() -> None:
    op.drop_index("ix_permits_location", table_name="permits", schema=SCHEMA)
    op.drop_table("permits", schema=SCHEMA)
    sa.Enum(name="usage_type", schema=SCHEMA).drop(op.get_bind(), checkfirst=True)
