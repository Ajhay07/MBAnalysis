"""add catalog_component_id/catalog_match_score to components, catalog_component_id to
bom_line_items (OCR-to-catalog matching, additive only)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-10-18 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('components') as batch_op:
        batch_op.add_column(sa.Column('catalog_component_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('catalog_match_score', sa.Float(), nullable=True))
        batch_op.create_foreign_key(
            'fk_components_catalog_component_id', 'catalog_components',
            ['catalog_component_id'], ['id'])

    with op.batch_alter_table('bom_line_items') as batch_op:
        batch_op.add_column(sa.Column('catalog_component_id', sa.String(), nullable=True))
        batch_op.create_foreign_key(
            'fk_bom_line_items_catalog_component_id', 'catalog_components',
            ['catalog_component_id'], ['id'])


def downgrade():
    with op.batch_alter_table('bom_line_items') as batch_op:
        batch_op.drop_constraint('fk_bom_line_items_catalog_component_id', type_='foreignkey')
        batch_op.drop_column('catalog_component_id')

    with op.batch_alter_table('components') as batch_op:
        batch_op.drop_constraint('fk_components_catalog_component_id', type_='foreignkey')
        batch_op.drop_column('catalog_match_score')
        batch_op.drop_column('catalog_component_id')
