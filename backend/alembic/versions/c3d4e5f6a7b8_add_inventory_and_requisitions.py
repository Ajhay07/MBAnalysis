"""add inventory lots, allocations, purchase requisitions

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-15 00:00:02.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'c3d4e5f6a7b8'
down_revision = 'b2c3d4e5f6a7'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('catalog_components', sa.Column('moq', sa.Float(), nullable=True))
    op.add_column('catalog_components', sa.Column('lead_time_days', sa.Integer(), nullable=True))

    op.create_table(
        'inventory_lots',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('material_code', sa.String(), nullable=True),
        sa.Column('material', sa.String(), nullable=True),
        sa.Column('grade', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('unit', sa.String(), nullable=True),
        sa.Column('on_hand_qty', sa.String(), nullable=True),
        sa.Column('reserved_qty', sa.String(), nullable=True),
        sa.Column('quarantined_qty', sa.String(), nullable=True),
        sa.Column('location', sa.String(), nullable=True),
        sa.Column('lot_number', sa.String(), nullable=True),
        sa.Column('supplier_id', sa.String(), sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('received_date', sa.DateTime(), nullable=True),
        sa.Column('is_demo', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_inventory_lots_material_code', 'inventory_lots', ['material_code'])

    op.create_table(
        'inventory_allocations',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('inventory_lot_id', sa.String(), sa.ForeignKey('inventory_lots.id'), nullable=False),
        sa.Column('bom_id', sa.String(), sa.ForeignKey('boms.id'), nullable=False),
        sa.Column('material_code', sa.String(), nullable=True),
        sa.Column('quantity', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
    )

    op.create_table(
        'purchase_requisitions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('bom_id', sa.String(), sa.ForeignKey('boms.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='Draft'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', sa.String(), nullable=True),
    )

    op.create_table(
        'purchase_requisition_lines',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('requisition_id', sa.String(), sa.ForeignKey('purchase_requisitions.id'), nullable=False),
        sa.Column('material_code', sa.String(), nullable=True),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('quantity', sa.String(), nullable=False),
        sa.Column('unit', sa.String(), nullable=True),
        sa.Column('supplier_id', sa.String(), sa.ForeignKey('suppliers.id'), nullable=True),
        sa.Column('catalog_component_id', sa.String(), sa.ForeignKey('catalog_components.id'), nullable=True),
        sa.Column('unit_cost', sa.Float(), nullable=True),
    )


def downgrade():
    op.drop_table('purchase_requisition_lines')
    op.drop_table('purchase_requisitions')
    op.drop_table('inventory_allocations')
    op.drop_index('ix_inventory_lots_material_code', table_name='inventory_lots')
    op.drop_table('inventory_lots')
    op.drop_column('catalog_components', 'lead_time_days')
    op.drop_column('catalog_components', 'moq')
