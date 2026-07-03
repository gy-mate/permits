"""Move permits.city_ksh_code into a local.hu table keyed by city_wikidata_id.

Revision ID: 0002_local_hu
Revises: 0001_initial
Create Date: 2026-06-30
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_local_hu"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

SCHEMA = "permits"
LOCAL_SCHEMA = "local"
FK_NAME = "fk_permits_city_wikidata_id"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {LOCAL_SCHEMA}")

    op.create_table(
        "hu",
        sa.Column("city_wikidata_id", sa.Text(), primary_key=True),
        sa.Column("ksh_code", sa.Text(), nullable=False),
        schema=LOCAL_SCHEMA,
    )

    # Fill the new table from data already in the permits table
    op.execute(
        f"INSERT INTO {LOCAL_SCHEMA}.hu (city_wikidata_id, ksh_code) "
        f"SELECT DISTINCT city_wikidata_id, city_ksh_code FROM {SCHEMA}.permits"
    )

    op.create_foreign_key(
        FK_NAME,
        "permits",
        "hu",
        ["city_wikidata_id"],
        ["city_wikidata_id"],
        source_schema=SCHEMA,
        referent_schema=LOCAL_SCHEMA,
    )

    op.drop_column("permits", "city_ksh_code", schema=SCHEMA)


def downgrade() -> None:
    op.add_column("permits", sa.Column("city_ksh_code", sa.Text(), nullable=True), schema=SCHEMA)

    op.execute(
        f"UPDATE {SCHEMA}.permits AS p "
        f"SET city_ksh_code = h.ksh_code FROM {LOCAL_SCHEMA}.hu AS h "
        f"WHERE h.city_wikidata_id = p.city_wikidata_id"
    )

    op.alter_column("permits", "city_ksh_code", nullable=False, schema=SCHEMA)

    op.drop_constraint(FK_NAME, "permits", schema=SCHEMA, type_="foreignkey")
    op.drop_table("hu", schema=LOCAL_SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {LOCAL_SCHEMA}")
