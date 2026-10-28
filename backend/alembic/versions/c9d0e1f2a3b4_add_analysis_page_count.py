"""add page_count to analyses (persisted actual processed-page count, additive only)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-10-28 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d0e1f2a3b4'
down_revision = 'b8c9d0e1f2a3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('analyses') as batch_op:
        batch_op.add_column(sa.Column('page_count', sa.Integer(), nullable=True, server_default='1'))
    # Backfill existing rows explicitly (server_default alone is enough for SQLite, but be
    # explicit so this also behaves correctly on a backend configured against another engine).
    op.execute("UPDATE analyses SET page_count = 1 WHERE page_count IS NULL")


def downgrade():
    with op.batch_alter_table('analyses') as batch_op:
        batch_op.drop_column('page_count')
