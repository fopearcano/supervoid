"""public bookshop catalogue fields on published_works

Revision ID: 0013_catalogue
Revises: 0012_indexes
Create Date: 2026-06-26 08:30:00.000000

Adds the public selling-catalogue fields to ``published_works`` (for_sale,
price_cents, currency, buy_url, format_label). NOT NULL additions carry a
server_default so existing rows backfill; SQLite goes through batch mode with a
naming convention (baseline FKs are unnamed) as in 0011.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel  # noqa: F401  (SQLModel column types, e.g. AutoString)

revision: str = '0013_catalogue'
down_revision: Union[str, None] = '0012_indexes'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table('published_works', schema=None, naming_convention=NAMING) as batch_op:
        batch_op.add_column(
            sa.Column('for_sale', sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(sa.Column('price_cents', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column('currency', sqlmodel.sql.sqltypes.AutoString(length=3),
                      nullable=False, server_default='EUR')
        )
        batch_op.add_column(
            sa.Column('buy_url', sqlmodel.sql.sqltypes.AutoString(length=600), nullable=True)
        )
        batch_op.add_column(
            sa.Column('format_label', sqlmodel.sql.sqltypes.AutoString(length=80), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('published_works', schema=None, naming_convention=NAMING) as batch_op:
        batch_op.drop_column('format_label')
        batch_op.drop_column('buy_url')
        batch_op.drop_column('currency')
        batch_op.drop_column('price_cents')
        batch_op.drop_column('for_sale')
