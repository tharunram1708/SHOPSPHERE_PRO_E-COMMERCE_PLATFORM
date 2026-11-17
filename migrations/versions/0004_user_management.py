"""Add user account status and permission grants.

Revision ID: 0004_user_management
Revises: 0003_auth_tokens
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_user_management"
down_revision = "0003_auth_tokens"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("status", sa.String(20), nullable=True))
    op.add_column("users", sa.Column("permissions_json", sa.Text(), nullable=True))
    op.execute("UPDATE users SET status = 'active' WHERE status IS NULL")
    op.execute("UPDATE users SET permissions_json = '[]' WHERE permissions_json IS NULL")
    op.alter_column("users", "status", existing_type=sa.String(20), nullable=False)
    op.alter_column("users", "permissions_json", existing_type=sa.Text(), nullable=False)
    op.create_index("ix_users_status", "users", ["status"])


def downgrade():
    op.drop_index("ix_users_status", table_name="users")
    op.drop_column("users", "permissions_json")
    op.drop_column("users", "status")
