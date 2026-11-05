"""Durable backup queue and weekly schedule."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0007_backups'
down_revision = '0006_opportunities'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('backup_schedule',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('next_run', sa.DateTime(timezone=True), nullable=False),
        sa.Column('heartbeat', sa.DateTime(timezone=True)),
        sa.CheckConstraint('id = 1', name='ck_backup_schedule_singleton'))
    op.create_table('backup_runs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True)),
        sa.Column('trigger', sa.String(12), nullable=False),
        sa.Column('status', sa.String(12), nullable=False),
        sa.Column('filename', sa.String(100)),
        sa.Column('size_bytes', sa.Numeric(20, 0)),
        sa.Column('error', sa.String(300)),
        sa.CheckConstraint("trigger IN ('manual','scheduled')", name='ck_backup_trigger'),
        sa.CheckConstraint("status IN ('queued','running','completed','failed','expired')", name='ck_backup_status'))
    op.create_index('ix_backup_runs_created_at', 'backup_runs', ['created_at'])


def downgrade():
    op.drop_table('backup_runs')
    op.drop_table('backup_schedule')
