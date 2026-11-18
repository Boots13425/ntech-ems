"""Shared opportunity logbook and work in progress."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '0008_opportunity_logbook'
down_revision = '0007_backups'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('opportunity_tasks', sa.Column('started_at', sa.DateTime(timezone=True)))
    op.create_table('opportunity_activities',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('opportunity_id', UUID(as_uuid=True), sa.ForeignKey('opportunities.id'), nullable=False),
        sa.Column('actor_id', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('action', sa.String(100), nullable=False),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('details', JSONB, nullable=False))
    op.create_index('ix_opportunity_activity_timeline', 'opportunity_activities', ['opportunity_id', 'occurred_at', 'id'])
    op.create_index('ix_opportunity_activities_actor_id', 'opportunity_activities', ['actor_id'])
    op.execute("""INSERT INTO opportunity_activities
        (id, created_at, updated_at, opportunity_id, actor_id, action, occurred_at, details)
        SELECT a.id, a.created_at, a.created_at, a.entity_id, a.actor_id, a.action, a.created_at, a.details
        FROM audit_events a JOIN opportunities o ON o.id = a.entity_id
        WHERE a.entity_type = 'opportunity'""")


def downgrade():
    op.drop_table('opportunity_activities')
    op.drop_column('opportunity_tasks', 'started_at')
