"""add calc_spec_identifier/calc_inputs/calc_result to components (engineering_engine
calculation-engine integration, additive only)

Revision ID: 599885c8f157
Revises: f6a7b8c9d0e1
Create Date: 2026-11-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '599885c8f157'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('components') as batch_op:
        batch_op.add_column(sa.Column('calc_spec_identifier', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('calc_inputs', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('calc_result', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('components') as batch_op:
        batch_op.drop_column('calc_result')
        batch_op.drop_column('calc_inputs')
        batch_op.drop_column('calc_spec_identifier')
