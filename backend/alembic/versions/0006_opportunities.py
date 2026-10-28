"""Opportunity pipeline, campaign links and assigned follow-up work."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '0006_opportunities'
down_revision = '0005_notifications'
branch_labels = None
depends_on = None


def entity():
    return [sa.Column('id', UUID(as_uuid=True), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table('opportunities', *entity(),
        sa.Column('title', sa.String(180), nullable=False),
        sa.Column('organization_id', UUID(as_uuid=True), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('creator_id', UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('owner_id', UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('stage', sa.String(20), nullable=False),
        sa.Column('estimated_value', sa.Numeric(16, 2)),
        sa.Column('currency', sa.String(3), nullable=False),
        sa.Column('expected_close', sa.Date()),
        sa.Column('loss_reason', sa.String(1000), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.CheckConstraint("stage IN ('new','qualified','proposal','negotiation','won','lost')", name='ck_opportunity_stage'),
        sa.CheckConstraint('estimated_value IS NULL OR estimated_value >= 0', name='ck_opportunity_value'),
        sa.CheckConstraint("stage != 'lost' OR length(trim(loss_reason)) > 0", name='ck_opportunity_loss_reason'))
    for column in ['organization_id', 'creator_id', 'owner_id', 'stage']:
        op.create_index(f'ix_opportunities_{column}', 'opportunities', [column])
    op.add_column('email_campaigns', sa.Column('opportunity_id', UUID(as_uuid=True), sa.ForeignKey('opportunities.id')))
    op.create_index('ix_email_campaigns_opportunity_id', 'email_campaigns', ['opportunity_id'])
    op.create_table('opportunity_sources', *entity(),
        sa.Column('opportunity_id', UUID(as_uuid=True), sa.ForeignKey('opportunities.id'), nullable=False),
        sa.Column('campaign_id', UUID(as_uuid=True), sa.ForeignKey('email_campaigns.id'), nullable=False),
        sa.Column('recipient_id', UUID(as_uuid=True), sa.ForeignKey('campaign_recipients.id'), nullable=False, unique=True))
    for column in ['opportunity_id', 'campaign_id']:
        op.create_index(f'ix_opportunity_sources_{column}', 'opportunity_sources', [column])
    op.create_table('opportunity_tasks', *entity(),
        sa.Column('opportunity_id', UUID(as_uuid=True), sa.ForeignKey('opportunities.id'), nullable=False),
        sa.Column('title', sa.String(180), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('due_notified', sa.Boolean(), nullable=False),
        sa.Column('overdue_notified', sa.Boolean(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False))
    for column in ['opportunity_id', 'due_at']:
        op.create_index(f'ix_opportunity_tasks_{column}', 'opportunity_tasks', [column])
    # The new staff surface is scoped to assigned work, not company-wide data.
    op.execute("""INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
        WHERE r.name='Staff' AND p.code='opportunities.read' ON CONFLICT DO NOTHING""")


def downgrade():
    op.drop_table('opportunity_tasks')
    op.drop_table('opportunity_sources')
    op.drop_column('email_campaigns', 'opportunity_id')
    op.drop_table('opportunities')
