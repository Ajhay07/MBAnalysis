"""add total_quantity rollup column to bom_line_items

Revision ID: a1b2c3d4e5f6
Revises: 7787f60a7a82
Create Date: 2026-10-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '7787f60a7a82'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('bom_line_items', sa.Column('total_quantity', sa.Float(), nullable=True))


def downgrade():
    op.drop_column('bom_line_items', 'total_quantity')
