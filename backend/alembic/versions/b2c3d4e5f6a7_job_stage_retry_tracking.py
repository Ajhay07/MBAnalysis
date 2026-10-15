"""add job stage/retry/failure tracking columns

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-15 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b2c3d4e5f6a7'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('jobs', sa.Column('analysis_id', sa.String(), nullable=True))
    op.add_column('jobs', sa.Column('stage', sa.String(), nullable=False, server_default='queued'))
    op.add_column('jobs', sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('jobs', sa.Column('last_error', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('failure_reason', sa.Text(), nullable=True))
    op.add_column('jobs', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('jobs', sa.Column('completed_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('jobs', 'completed_at')
    op.drop_column('jobs', 'started_at')
    op.drop_column('jobs', 'failure_reason')
    op.drop_column('jobs', 'last_error')
    op.drop_column('jobs', 'retry_count')
    op.drop_column('jobs', 'stage')
    op.drop_column('jobs', 'analysis_id')
