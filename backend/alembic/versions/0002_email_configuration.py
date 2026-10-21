"""Company SMTP configuration with encrypted credentials."""
from alembic import op
import sqlalchemy as sa

revision = "0002_email_configuration"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "email_configuration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("host", sa.String(253), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("security", sa.String(10), nullable=False),
        sa.Column("sender_name", sa.String(150), nullable=False),
        sa.Column("sender_email", sa.String(254), nullable=False),
        sa.Column("username_encrypted", sa.Text()),
        sa.Column("password_encrypted", sa.Text()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_email_configuration_singleton"),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_email_configuration_port"),
        sa.CheckConstraint("security IN ('starttls', 'tls', 'none')", name="ck_email_configuration_security"),
    )


def downgrade():
    op.drop_table("email_configuration")
