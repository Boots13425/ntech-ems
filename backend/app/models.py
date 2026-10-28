import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Index, Integer, String, Table, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class EmailConfiguration(Base):
    __tablename__ = "email_configuration"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    host: Mapped[str] = mapped_column(String(253))
    port: Mapped[int] = mapped_column(Integer)
    security: Mapped[str] = mapped_column(String(10))
    sender_name: Mapped[str] = mapped_column(String(150))
    sender_email: Mapped[str] = mapped_column(String(254))
    username_encrypted: Mapped[str | None] = mapped_column(Text)
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    imap_host: Mapped[str | None] = mapped_column(String(253))
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    imap_username_encrypted: Mapped[str | None] = mapped_column(Text)
    imap_password_encrypted: Mapped[str | None] = mapped_column(Text)
    hourly_limit: Mapped[int] = mapped_column(Integer, default=50)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_email_configuration_singleton"),
        CheckConstraint("port BETWEEN 1 AND 65535", name="ck_email_configuration_port"),
        CheckConstraint("security IN ('starttls', 'tls', 'none')", name="ck_email_configuration_security"),
    )


def association(name, left, right):
    tables = {"responsibility": "responsibilities"}
    return Table(name, Base.metadata,
                 Column(f"{left}_id", UUID(as_uuid=True), ForeignKey(f"{tables.get(left, left + 's')}.id", ondelete="CASCADE"), primary_key=True),
                 Column(f"{right}_id", UUID(as_uuid=True), ForeignKey(f"{tables.get(right, right + 's')}.id", ondelete="CASCADE"), primary_key=True))


user_roles = association("user_roles", "user", "role")
role_permissions = association("role_permissions", "role", "permission")
user_responsibilities = association("user_responsibilities", "user", "responsibility")
responsibility_permissions = association("responsibility_permissions", "responsibility", "permission")


class Entity:
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Permission(Entity, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(100), unique=True)


class Role(Entity, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(40), unique=True)
    permissions: Mapped[list[Permission]] = relationship(secondary=role_permissions, lazy="selectin")


class Responsibility(Entity, Base):
    __tablename__ = "responsibilities"
    name: Mapped[str] = mapped_column(String(80), unique=True)
    permissions: Mapped[list[Permission]] = relationship(secondary=responsibility_permissions, lazy="selectin")


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    full_name: Mapped[str] = mapped_column(String(150))
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mfa_last_counter: Mapped[int | None] = mapped_column(Integer)
    roles: Mapped[list[Role]] = relationship(secondary=user_roles, lazy="selectin")
    responsibilities: Mapped[list[Responsibility]] = relationship(secondary=user_responsibilities, lazy="selectin")


class Session(Entity, Base):
    __tablename__ = "sessions"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    state: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    user: Mapped[User] = relationship(lazy="joined")


class RecoveryCode(Entity, Base):
    __tablename__ = "recovery_codes"
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)


class AuthAttempt(Entity, Base):
    __tablename__ = "auth_attempts"
    key: Mapped[str] = mapped_column(String(64), index=True)
    __table_args__ = (Index("ix_auth_attempt_window", "key", "created_at"),)


class Classification(Entity, Base):
    __tablename__ = "classifications"
    name: Mapped[str] = mapped_column(String(30), unique=True)


organization_classifications = Table("organization_classifications", Base.metadata,
    Column("organization_id", UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), primary_key=True),
    Column("classification_id", UUID(as_uuid=True), ForeignKey("classifications.id", ondelete="CASCADE"), primary_key=True))


class Organization(Entity, Base):
    __tablename__ = "organizations"
    name: Mapped[str] = mapped_column(String(180))
    normalized_name: Mapped[str] = mapped_column(String(180), unique=True)
    industry: Mapped[str | None] = mapped_column(String(100), index=True)
    country: Mapped[str] = mapped_column(String(100), default="Cameroon", index=True)
    city: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    website: Mapped[str | None] = mapped_column(String(500))
    address: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    classifications: Mapped[list[Classification]] = relationship(secondary=organization_classifications, lazy="selectin")
    contacts: Mapped[list["Contact"]] = relationship(back_populates="organization", cascade="all, delete-orphan", lazy="selectin")
    partner_profile: Mapped["PartnerProfile | None"] = relationship(back_populates="organization", uselist=False, cascade="all, delete-orphan", lazy="selectin")
    __table_args__ = (CheckConstraint("length(trim(name)) >= 2", name="ck_organization_name"),)


class Contact(Entity, Base):
    __tablename__ = "contacts"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    job_title: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    organization: Mapped[Organization] = relationship(back_populates="contacts")
    __table_args__ = (
        UniqueConstraint("organization_id", "email", name="uq_contact_org_email"),
        Index("uq_contact_primary", "organization_id", unique=True, postgresql_where=Column("is_primary", Boolean) == True),
    )


partner_capability_links = Table("partner_capability_links", Base.metadata,
    Column("partner_id", UUID(as_uuid=True), ForeignKey("partner_profiles.id", ondelete="CASCADE"), primary_key=True),
    Column("capability_id", UUID(as_uuid=True), ForeignKey("partner_capabilities.id", ondelete="CASCADE"), primary_key=True))


class PartnerCapability(Entity, Base):
    __tablename__ = "partner_capabilities"
    name: Mapped[str] = mapped_column(String(120), unique=True)


class PartnerProfile(Entity, Base):
    __tablename__ = "partner_profiles"
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(30), default="prospective")
    category: Mapped[str | None] = mapped_column(String(100))
    commercial_model: Mapped[str | None] = mapped_column(String(100))
    organization: Mapped[Organization] = relationship(back_populates="partner_profile")
    capabilities: Mapped[list[PartnerCapability]] = relationship(secondary=partner_capability_links, lazy="selectin")


class AuditEvent(Entity, Base):
    __tablename__ = "audit_events"
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizations.id"), index=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (Index("ix_audit_org_time", "organization_id", "created_at"),)


class EmailTemplate(Entity, Base):
    __tablename__ = "email_templates"
    name: Mapped[str] = mapped_column(String(150))
    category: Mapped[str] = mapped_column(String(60))
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")


class EmailCampaign(Entity, Base):
    __tablename__ = "email_campaigns"
    name: Mapped[str] = mapped_column(String(150))
    objective: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(Text, default="")
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    steps: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(25), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    approved_version: Mapped[int | None] = mapped_column(Integer)
    sender_email: Mapped[str | None] = mapped_column(String(254))
    sender_name: Mapped[str | None] = mapped_column(String(150))
    issue: Mapped[str | None] = mapped_column(Text)


class CampaignRecipient(Entity, Base):
    __tablename__ = "campaign_recipients"
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_campaigns.id"), index=True)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("contacts.id", ondelete="SET NULL"), index=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    email: Mapped[str] = mapped_column(String(254), index=True)
    variables: Mapped[dict] = mapped_column(JSONB)
    outcome: Mapped[str] = mapped_column(String(30), default="pending")
    stopped: Mapped[bool] = mapped_column(Boolean, default=False)
    outreach_active: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (UniqueConstraint("campaign_id", "email", name="uq_campaign_email"),
                     Index("uq_active_outreach_email", "email", unique=True, postgresql_where=Column("outreach_active", Boolean) == True))


class CampaignApproval(Entity, Base):
    __tablename__ = "campaign_approvals"
    campaign_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("email_campaigns.id"), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(20))
    note: Mapped[str] = mapped_column(Text, default="")


class OutboundEmail(Entity, Base):
    __tablename__ = "outbound_emails"
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign_recipients.id"), index=True)
    step: Mapped[int] = mapped_column(Integer)
    subject: Mapped[str] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text)
    message_id: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (UniqueConstraint("recipient_id", "step", name="uq_recipient_step"),)


class InboundEmail(Entity, Base):
    __tablename__ = "inbound_emails"
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("campaign_recipients.id"), index=True)
    mailbox_key: Mapped[str] = mapped_column(String(100), unique=True)
    message_id: Mapped[str | None] = mapped_column(String(998))
    subject: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    sender: Mapped[str] = mapped_column(String(254))


class EmailSuppression(Entity, Base):
    __tablename__ = "email_suppressions"
    email: Mapped[str] = mapped_column(String(254), unique=True)
    reason: Mapped[str] = mapped_column(String(300))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))


class MailboxSyncState(Base):
    __tablename__ = "mailbox_sync_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    identity: Mapped[str] = mapped_column(String(64), default="")
    uid_validity: Mapped[str] = mapped_column(String(40), default="")
    last_uid: Mapped[int] = mapped_column(Integer, default=0)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class CampaignWorkerState(Base):
    __tablename__ = "campaign_worker_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phase: Mapped[str] = mapped_column(String(30))
    error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("id = 1", name="ck_campaign_worker_singleton"),)


class Notification(Entity, Base):
    __tablename__ = "notifications"
    recipient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(150))
    message: Mapped[str] = mapped_column(Text)
    path: Mapped[str] = mapped_column(String(200))
    required_permission: Mapped[str | None] = mapped_column(String(100))
    reviewer_only: Mapped[bool] = mapped_column(Boolean, default=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_notifications_recipient_created", "recipient_id", "created_at", "id"),
        Index("ix_notifications_unread", "recipient_id", postgresql_where=read_at.is_(None)),
    )
