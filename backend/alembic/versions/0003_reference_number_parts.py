"""Split permits.reference_number into its parts; give local.hu an id and an authority_id.

``local.hu`` gains a surrogate ``id`` primary key (``city_wikidata_id`` stays unique
and remains the foreign-key target) plus a ``local_authority_id`` column, set to
``FPH`` for Budapest. ``permits.reference_number`` ('58-2712/4/25') is replaced by
``department_id`` / ``main_registration_number`` / ``sub_registration_number`` /
``year_number`` columns, with the century inferred from ``time_from``.
``time_from`` and ``time_to`` become NOT NULL.

Revision ID: 0003_reference_number_parts
Revises: 0002_local_hu
Create Date: 2026-07-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0003_reference_number_parts"
down_revision = "0002_local_hu"
branch_labels = None
depends_on = None

SCHEMA = "permits"
LOCAL_SCHEMA = "local"
FK_NAME = "fk_permits_city_wikidata_id"


def upgrade() -> None:
    # local.hu: move the primary key to a new id; the foreign key from
    # permits keeps pointing at city_wikidata_id, which becomes a unique column
    op.drop_constraint(FK_NAME, "permits", schema=SCHEMA, type_="foreignkey")
    op.drop_constraint("hu_pkey", "hu", schema=LOCAL_SCHEMA, type_="primary")
    op.add_column(
        "hu", sa.Column("id", sa.Integer(), sa.Identity(), nullable=False), schema=LOCAL_SCHEMA
    )
    op.create_primary_key("hu_pkey", "hu", ["id"], schema=LOCAL_SCHEMA)
    op.create_unique_constraint(
        "uq_hu_city_wikidata_id", "hu", ["city_wikidata_id"], schema=LOCAL_SCHEMA
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

    op.add_column(
        "hu", sa.Column("local_authority_id", sa.Text(), nullable=True), schema=LOCAL_SCHEMA
    )
    op.execute(f"UPDATE {LOCAL_SCHEMA}.hu SET local_authority_id = 'FPH' WHERE ksh_code = 'budap'")
    op.alter_column("hu", "local_authority_id", nullable=False, schema=LOCAL_SCHEMA)

    # permits: split reference_number ('58-2712/4/25') into its four parts
    op.add_column("permits", sa.Column("department_id", sa.Integer(), nullable=True), schema=SCHEMA)
    op.add_column(
        "permits", sa.Column("main_registration_number", sa.Integer(), nullable=True), schema=SCHEMA
    )
    op.add_column(
        "permits", sa.Column("sub_registration_number", sa.Integer(), nullable=True), schema=SCHEMA
    )
    op.add_column("permits", sa.Column("year_number", sa.Integer(), nullable=True), schema=SCHEMA)

    op.execute(
        f"""
        UPDATE {SCHEMA}.permits SET
            department_id = split_part(reference_number, '-', 1)::int,
            main_registration_number = NULLIF(split_part(split_part(reference_number, '/', 1), '-', 2), '')::int,
            sub_registration_number = split_part(reference_number, '/', 2)::int,
            year_number = (EXTRACT(YEAR FROM time_from)::int / 100) * 100
                          + split_part(reference_number, '/', 3)::int
        """
    )

    op.alter_column("permits", "time_from", nullable=False, schema=SCHEMA)
    op.alter_column("permits", "time_to", nullable=False, schema=SCHEMA)

    op.alter_column("permits", "sub_registration_number", nullable=False, schema=SCHEMA)
    op.alter_column("permits", "year_number", nullable=False, schema=SCHEMA)

    op.drop_constraint("uq_permits_reference_number", "permits", schema=SCHEMA, type_="unique")
    op.drop_column("permits", "reference_number", schema=SCHEMA)


def downgrade() -> None:
    op.add_column(
        "permits", sa.Column("reference_number", sa.Text(), nullable=True), schema=SCHEMA
    )
    op.execute(
        f"""
        UPDATE {SCHEMA}.permits SET reference_number =
            department_id || '-' || coalesce(main_registration_number::text, '') || '/'
            || sub_registration_number || '/' || lpad((year_number % 100)::text, 2, '0')
        """
    )

    op.alter_column("permits", "reference_number", nullable=False, schema=SCHEMA)
    op.create_unique_constraint(
        "uq_permits_reference_number", "permits", ["reference_number"], schema=SCHEMA
    )

    op.alter_column("permits", "time_from", nullable=True, schema=SCHEMA)
    op.alter_column("permits", "time_to", nullable=True, schema=SCHEMA)

    op.drop_column("permits", "year_number", schema=SCHEMA)
    op.drop_column("permits", "sub_registration_number", schema=SCHEMA)
    op.drop_column("permits", "main_registration_number", schema=SCHEMA)
    op.drop_column("permits", "department_id", schema=SCHEMA)

    op.drop_column("hu", "local_authority_id", schema=LOCAL_SCHEMA)

    op.drop_constraint(FK_NAME, "permits", schema=SCHEMA, type_="foreignkey")
    op.drop_constraint("uq_hu_city_wikidata_id", "hu", schema=LOCAL_SCHEMA, type_="unique")
    op.drop_constraint("hu_pkey", "hu", schema=LOCAL_SCHEMA, type_="primary")

    op.drop_column("hu", "id", schema=LOCAL_SCHEMA)

    op.create_primary_key("hu_pkey", "hu", ["city_wikidata_id"], schema=LOCAL_SCHEMA)
    op.create_foreign_key(
        FK_NAME,
        "permits",
        "hu",
        ["city_wikidata_id"],
        ["city_wikidata_id"],
        source_schema=SCHEMA,
        referent_schema=LOCAL_SCHEMA,
    )
