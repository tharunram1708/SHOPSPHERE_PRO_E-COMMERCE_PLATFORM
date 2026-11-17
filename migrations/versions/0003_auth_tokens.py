"""Persist access and refresh token identifiers for rotation and revocation.

Revision ID: 0003_auth_tokens
Revises: 0002_advanced_order_fulfillment
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_auth_tokens"
down_revision = "0002_order_fulfillment"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("jti", sa.String(36), nullable=False, unique=True),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_type", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_auth_tokens_jti", "auth_tokens", ["jti"], unique=True)
    op.create_index("ix_auth_tokens_session_id", "auth_tokens", ["session_id"])
    op.create_index("ix_auth_tokens_user_id", "auth_tokens", ["user_id"])


def downgrade():
    op.drop_index("ix_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_session_id", table_name="auth_tokens")
    op.drop_index("ix_auth_tokens_jti", table_name="auth_tokens")
    op.drop_table("auth_tokens")
