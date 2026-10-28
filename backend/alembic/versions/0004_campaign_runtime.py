"""Persist campaign processing health for automatic API-managed workers."""
from alembic import op
import sqlalchemy as sa

revision = '0004_campaign_runtime'
down_revision = '0003_campaigns'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('campaign_worker_state',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('last_heartbeat', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_completed', sa.DateTime(timezone=True)),
        sa.Column('phase', sa.String(30), nullable=False),
        sa.Column('error', sa.Text()),
        sa.CheckConstraint('id = 1', name='ck_campaign_worker_singleton'))


def downgrade():
    op.drop_table('campaign_worker_state')
