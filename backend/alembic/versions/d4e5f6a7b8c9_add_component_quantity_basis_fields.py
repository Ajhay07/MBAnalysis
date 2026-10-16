"""add quantity_basis/component_type/parent_part_number/is_assumption/assumption_text to components

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('components', sa.Column('quantity_basis', sa.String(), nullable=True))
    op.add_column('components', sa.Column('component_type', sa.String(), nullable=True))
    op.add_column('components', sa.Column('parent_part_number', sa.String(), nullable=True))
    op.add_column('components', sa.Column('is_assumption', sa.Boolean(), nullable=True))
    op.add_column('components', sa.Column('assumption_text', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('components', 'assumption_text')
    op.drop_column('components', 'is_assumption')
    op.drop_column('components', 'parent_part_number')
    op.drop_column('components', 'component_type')
    op.drop_column('components', 'quantity_basis')
