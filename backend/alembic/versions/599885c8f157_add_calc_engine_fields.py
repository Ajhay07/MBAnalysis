"""add calc_spec_identifier/calc_inputs/calc_result to components (engineering_engine
calculation-engine integration, additive only)

Revision ID: 599885c8f157
Revises: c9d0e1f2a3b4
Create Date: 2026-11-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '599885c8f157'
# Originally branched off f6a7b8c9d0e1 (a branchpoint - c9d0e1f2a3b4/b8c9d0e1f2a3/a7b8c9d0e1f2
# also descend from it) instead of the actual tip, leaving two unmerged alembic heads
# (599885c8f157 and c9d0e1f2a3b4). `alembic upgrade head` refuses to run with multiple heads -
# this is what was crash-looping every production deploy ("Multiple head revisions are present
# for given argument 'head'"). Rechained onto c9d0e1f2a3b4 (the real tip: adds page_count to
# analyses) so there is a single linear chain again; this doesn't change what either migration
# does, only where 599885c8f157 sits in the sequence.
down_revision = 'c9d0e1f2a3b4'
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
