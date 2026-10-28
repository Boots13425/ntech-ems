"""Private, persistent in-app notifications."""
from alembic import op
from datetime import datetime, timezone
from uuid import uuid4
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0005_notifications'
down_revision = '0004_campaign_runtime'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recipient_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(80), nullable=False),
        sa.Column('title', sa.String(150), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('path', sa.String(200), nullable=False),
        sa.Column('required_permission', sa.String(100)),
        sa.Column('reviewer_only', sa.Boolean(), nullable=False),
        sa.Column('read_at', sa.DateTime(timezone=True)))
    op.create_index('ix_notifications_recipient_created', 'notifications', ['recipient_id', 'created_at', 'id'])
    op.create_index('ix_notifications_unread', 'notifications', ['recipient_id'], postgresql_where=sa.text('read_at IS NULL'))
    # Existing submissions must also appear when this feature is deployed.
    connection = op.get_bind()
    pending = connection.execute(sa.text('''
        SELECT c.id, c.name, u.id AS recipient_id
        FROM email_campaigns c CROSS JOIN users u
        WHERE c.status = 'pending_approval' AND u.is_active AND u.id <> c.owner_id
        AND EXISTS (SELECT 1 FROM user_roles ur JOIN roles r ON r.id = ur.role_id
                    WHERE ur.user_id = u.id AND r.name IN ('CEO', 'Manager'))
        AND (EXISTS (SELECT 1 FROM user_roles ur JOIN role_permissions rp ON rp.role_id = ur.role_id
                     JOIN permissions p ON p.id = rp.permission_id
                     WHERE ur.user_id = u.id AND p.code = 'campaigns.read')
             OR EXISTS (SELECT 1 FROM user_responsibilities ur
                        JOIN responsibility_permissions rp ON rp.responsibility_id = ur.responsibility_id
                        JOIN permissions p ON p.id = rp.permission_id
                        WHERE ur.user_id = u.id AND p.code = 'campaigns.read'))
    ''')).mappings()
    for row in pending:
        connection.execute(sa.text('''INSERT INTO notifications
            (id, created_at, updated_at, recipient_id, kind, title, message, path, required_permission, reviewer_only)
            VALUES (:id, :now, :now, :recipient, 'campaign.submitted', 'Campaign submitted for approval',
                    :message, :path, 'campaigns.read', true)'''),
            dict(id=uuid4(), now=datetime.now(timezone.utc), recipient=row['recipient_id'],
                 message=f'“{row["name"]}” is awaiting review and approval.', path=f'/campaigns/{row["id"]}'))


def downgrade():
    op.drop_table('notifications')
