"""Add split fulfillment, backorders, cancellations and order timeline.

Revision ID: 0002_order_fulfillment
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_order_fulfillment"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    # Existing order lines were fully reserved at placement in the original API.
    for column in ("allocated_quantity", "shipped_quantity", "cancelled_quantity", "backordered_quantity"):
        op.add_column("order_lines", sa.Column(column, sa.Integer(), nullable=False, server_default="0"))
    op.execute("UPDATE order_lines SET allocated_quantity = quantity")
    for column in ("allocated_quantity", "shipped_quantity", "cancelled_quantity", "backordered_quantity"):
        op.alter_column("order_lines", column, existing_type=sa.Integer(), server_default=None)

    op.create_table("order_status_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("from_status", sa.String(24), nullable=True),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_order_status_history_order_id", "order_status_history", ["order_id"])
    op.execute("""
        INSERT INTO order_status_history (order_id, actor_id, from_status, to_status, reason, created_at)
        SELECT id, customer_id, NULL, status, 'Existing order status imported during Phase 2 migration', created_at
        FROM orders
    """)

    op.create_table("order_activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_line_id", sa.Integer(), sa.ForeignKey("order_lines.id"), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_order_activities_order_id", "order_activities", ["order_id"])

    op.create_table("shipments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("carrier", sa.String(100), nullable=True),
        sa.Column("tracking_number", sa.String(120), nullable=True),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("shipped_at", sa.DateTime(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("delivered_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("delivery_reason", sa.Text(), nullable=True))
    op.create_index("ix_shipments_order_id", "shipments", ["order_id"])

    op.create_table("shipment_lines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("shipment_id", sa.Integer(), sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("order_line_id", sa.Integer(), sa.ForeignKey("order_lines.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False))


def downgrade():
    op.drop_table("shipment_lines")
    op.drop_index("ix_shipments_order_id", table_name="shipments")
    op.drop_table("shipments")
    op.drop_index("ix_order_activities_order_id", table_name="order_activities")
    op.drop_table("order_activities")
    op.drop_index("ix_order_status_history_order_id", table_name="order_status_history")
    op.drop_table("order_status_history")
    op.drop_column("order_lines", "backordered_quantity")
    op.drop_column("order_lines", "cancelled_quantity")
    op.drop_column("order_lines", "shipped_quantity")
    op.drop_column("order_lines", "allocated_quantity")
