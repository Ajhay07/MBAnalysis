"""add indent_rules, indents, indent_lines tables (MB Metallic Bellows indent sheet
generation, additive only - no existing tables touched)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-10-26 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b8c9d0e1f2a3'
down_revision = 'a7b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'indent_rules',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('mtl_spec', sa.String(), nullable=True),
        sa.Column('size_text', sa.String(), nullable=True),
        sa.Column('unit', sa.String(), nullable=True),
        sa.Column('formula', sa.Enum('fixed_qty', 'per_assembly', 'manual_required', name='indentruleformula'),
                   nullable=False),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'indents',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('bom_id', sa.String(), sa.ForeignKey('boms.id'), nullable=False),
        sa.Column('drawing_id', sa.String(), sa.ForeignKey('drawings.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=True),
        sa.Column('wo_number', sa.String(), nullable=True),
        sa.Column('party_name', sa.String(), nullable=True),
        sa.Column('required_on', sa.String(), nullable=True),
        sa.Column('serial_no', sa.String(), nullable=True),
        sa.Column('indent_date', sa.String(), nullable=True),
        sa.Column('assembly_quantity', sa.Float(), nullable=False),
        sa.Column('status', sa.Enum('Draft', 'Approved', 'Rejected', name='indentstatus'), nullable=False),
        sa.Column('created_by', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('approved_by', sa.String(), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'indent_lines',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('indent_id', sa.String(), sa.ForeignKey('indents.id'), nullable=False),
        sa.Column('sl_no', sa.Integer(), nullable=False),
        sa.Column('mtl_spec', sa.String(), nullable=True),
        sa.Column('size_text', sa.String(), nullable=True),
        sa.Column('wt_qty', sa.Float(), nullable=True),
        sa.Column('unit', sa.String(), nullable=True),
        sa.Column('bom_line_item_id', sa.String(), sa.ForeignKey('bom_line_items.id'), nullable=True),
        sa.Column('indent_rule_id', sa.String(), sa.ForeignKey('indent_rules.id'), nullable=True),
        sa.Column('source', sa.String(), nullable=True),
        sa.Column('requires_confirmation', sa.Boolean(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table('indent_lines')
    op.drop_table('indents')
    op.drop_table('indent_rules')
