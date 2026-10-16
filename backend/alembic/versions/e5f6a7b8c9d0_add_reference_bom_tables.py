"""add reference_bom_tables table (reference BOM table detection, additive only)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-16 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'reference_bom_tables',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('analysis_id', sa.String(), sa.ForeignKey('analyses.id'), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('matched_headers', sa.JSON(), nullable=True),
        sa.Column('bbox', sa.JSON(), nullable=True),
        sa.Column('raw_text', sa.Text(), nullable=True),
        sa.Column('row_count_estimate', sa.Integer(), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=True),
    )


def downgrade():
    op.drop_table('reference_bom_tables')
