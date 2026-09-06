"""LeadPilot database models — Milestone 1 / Chunk 2.

Implements every table from project knowledge section G:
users, products, past_clients, strategies, research_steps, leads,
sequences, messages, outcomes, playbook_scores, suppression_list.

Design rules applied here:
- UUID primary keys (client-generated, portable across Postgres/SQLite
  so the test suite can run on SQLite with zero model changes).
- All enums are stored as VARCHAR (native_enum=False): adding a value
  later is a data-free migration, and SQLite tests behave identically.
- created_at/updated_at on every mutable table (TimestampMixin).
- research_steps has a UNIQUE (strategy_id, pipeline, step_no) —
  the schema itself guarantees "resume never duplicates a step".
- leads has UNIQUE (strategy_id, email) and (strategy_id, external_id)
  so M2's dedupe rule is enforced at the database level too.
- suppression_list rows must carry an email or a phone (CHECK).
"""

import enum
import uuid
from datetime import datetime, time, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# --------------------------------------------------------------------------
# Enums (stored as VARCHAR — see module docstring)
# --------------------------------------------------------------------------


class PlanTier(str, enum.Enum):
    FREE = "free"
    STARTER = "starter"      # M8-C5 plan enforcement tier
    PRO = "pro"
    ENTERPRISE = "enterprise"


class ProductType(str, enum.Enum):
    PRODUCT = "product"
    SKILL = "skill"


class FlowType(str, enum.Enum):
    WITH_CLIENTS = "with_clients"  # Flow 1: 72-step strategy pipeline
    NO_CLIENTS = "no_clients"      # Flow 2: 72 strategy + 72 GTM = 144 steps


class StrategyStatus(str, enum.Enum):
    PENDING = "pending"                      # created, pipeline not started
    RESEARCHING = "researching"              # pipeline running
    VERIFYING = "verifying"                  # 10x verification loop running
    VERIFIED = "verified"                    # all 10 passes green — may execute
    NEEDS_HUMAN_REVIEW = "needs_human_review"  # a pass hit its retry cap
    EXECUTING = "executing"                  # M2+: lead sourcing/outreach live
    FAILED = "failed"                        # unrecoverable pipeline error


class PipelineKind(str, enum.Enum):
    STRATEGY = "strategy"  # the core 72 (phases 1-8)
    GTM = "gtm"            # the second 72, Flow 2 only


class LeadStatus(str, enum.Enum):
    # M2 sourcing chain: sourced -> enriched -> email_found -> verified|flagged|dropped
    SOURCED = "sourced"
    ENRICHED = "enriched"
    EMAIL_FOUND = "email_found"
    VERIFIED = "verified"      # Hunter: deliverable
    FLAGGED = "flagged"        # Hunter: risky
    DROPPED = "dropped"        # Hunter: undeliverable / suppressed
    # M3+ outreach lifecycle:
    CONTACTED = "contacted"
    REPLIED = "replied"
    MEETING_BOOKED = "meeting_booked"


class BatchStage(str, enum.Enum):
    """Lifecycle of an M2 lead-sourcing batch (resumable per stage)."""
    SOURCING = "sourcing"
    ENRICHING = "enriching"
    FINDING_EMAILS = "finding_emails"
    VERIFYING = "verifying"
    FINALIZED = "finalized"
    FAILED = "failed"


class ChannelType(str, enum.Enum):
    EMAIL = "email"
    WHATSAPP = "whatsapp"
    LINKEDIN = "linkedin"


class SequenceStatus(str, enum.Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"


class MessageStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    SENDING = "sending"     # claimed by a send task (idempotency guard)
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BOUNCED = "bounced"
    # M4 Chunk 3:
    SKIPPED = "skipped"            # engine skipped (e.g. no WhatsApp opt-in);
                                   # the sequence CONTINUES to its next step
    NEEDS_TEMPLATE = "needs_template"  # free-form send failed closed (24h
                                   # window expired) or template no longer
                                   # approved — needs user attention"


class EnrollmentStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"       # e.g. out-of-office; auto-resumes at paused_until
    STOPPED = "stopped"     # hard stop — can NEVER send again for this lead
    COMPLETED = "completed"  # all steps sent


class OutcomeEvent(str, enum.Enum):
    SENT = "sent"
    OPENED = "opened"
    REPLIED = "replied"
    BOOKED = "booked"
    WON = "won"
    LOST = "lost"
    BOUNCED = "bounced"
    UNSUBSCRIBED = "unsubscribed"
    # M4/M7/M8 additions (VARCHAR-backed enum — data-free change)
    OPTED_OUT = "opted_out"            # WhatsApp STOP
    NOTIFICATION_SENT = "notification_sent"  # M7 push audit
    CIRCUIT_OPENED = "circuit_opened"  # M8-C3 circuit breaker audit
    AB_PROMOTED = "ab_promoted"        # M8-C2 promotion idempotency marker


class WhatsAppTemplateStatus(str, enum.Enum):
    """Lifecycle of a Meta message template (M4). Only APPROVED templates
    may ever be sent to cold contacts — enforced by the adapter + Chunk 2
    management flows."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"


class WhatsAppTemplateCategory(str, enum.Enum):
    """Meta template categories relevant to outreach.
    # TODO: verify against current WhatsApp docs (exact category values;
    Meta also has AUTHENTICATION, which LeadPilot deliberately never uses)."""
    MARKETING = "marketing"
    UTILITY = "utility"


class WhatsAppStepKind(str, enum.Enum):
    """How a WhatsApp sequence step sends (M4 Chunk 3).
    TEMPLATE: Meta-approved template — the only kind allowed cold.
    TEXT: free-form — ONLY dispatches inside an open 24h customer-service
    window (reply-handling steps); fails closed to needs_template."""
    TEMPLATE = "template"
    TEXT = "text"


class OptInStatus(str, enum.Enum):
    OPTED_IN = "opted_in"
    OPTED_OUT = "opted_out"
    UNKNOWN = "unknown"


class OptInSource(str, enum.Enum):
    WEB_FORM = "web_form"              # hosted /optin/whatsapp/{token} page
    INBOUND_MESSAGE = "inbound_message"  # the prospect messaged US first
    MANUAL_IMPORT = "manual_import"    # CSV import — evidence REQUIRED
    API = "api"                        # recorded via the opt-in API


# --------------------------------------------------------------------------
# M9 — native CRM layer
# --------------------------------------------------------------------------


class CrmActivityKind(str, enum.Enum):
    """What a `crm_activities` row records.

    Deliberately NOT the same vocabulary as OutcomeEvent. `outcomes` is the
    learning loop's immutable event log (M8 aggregates it nightly and the A/B
    sweep reads it); this is a UI-facing audit trail of what a HUMAN or the
    pipeline did to a lead. Some events exist in both — a reply produces an
    OutcomeEvent.REPLIED for the learning loop AND a REPLY_RECEIVED row for
    the activity feed — because collapsing them would mean either polluting
    the learning loop with note-added noise or losing the feed's notes.
    """
    LEAD_CREATED = "lead_created"
    STATUS_CHANGED = "status_changed"
    NOTE_ADDED = "note_added"
    NOTE_DELETED = "note_deleted"
    TAG_ADDED = "tag_added"
    TAG_REMOVED = "tag_removed"
    FIELD_CHANGED = "field_changed"      # custom field or crm_lead_meta edit
    OWNER_CHANGED = "owner_changed"
    REPLY_RECEIVED = "reply_received"
    MEETING_BOOKED = "meeting_booked"
    # Engagement Hub. Both are VARCHAR-backed additions to an existing enum,
    # which is a data-free change (see the module docstring) -- no migration
    # touches this column.
    MEETING_COMPLETED = "meeting_completed"
    TASK_CREATED = "task_created"


class CrmViewType(str, enum.Enum):
    DASHBOARD = "dashboard"
    GRID = "grid"


class CrmFieldType(str, enum.Enum):
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    BOOL = "bool"
    SELECT = "select"


# --------------------------------------------------------------------------
# Engagement Hub — calendar, bookings, meetings
# --------------------------------------------------------------------------


class BookingStatus(str, enum.Enum):
    """Lifecycle of one slot booked on a public booking page.

    CANCELLED is a soft delete: DELETE /calendar/bookings/{id} sets this and
    clears `slot_key`, which both frees the slot for someone else and keeps
    the row for the lead's timeline. A cancelled meeting that vanished from
    history would take its CRM activity with it.
    """
    PENDING = "pending"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class MeetingPlatform(str, enum.Enum):
    """Where the call actually happens.

    CUSTOM is not a fallback for "we could not integrate" -- it is the
    platform-agnostic path the product promises: paste any join URL (Whereby,
    a phone bridge, the client's own Webex) and LeadPilot still runs the
    notes, transcript and summary around it.
    """
    GOOGLE_MEET = "google_meet"
    ZOOM = "zoom"
    TEAMS = "teams"
    CUSTOM = "custom"


class MeetingStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class MeetingParticipantRole(str, enum.Enum):
    HOST = "host"
    CLIENT = "client"
    OBSERVER = "observer"


def _enum(e: type[enum.Enum]) -> Enum:
    """VARCHAR-backed enum column storing the enum *values*."""
    return Enum(
        e,
        native_enum=False,
        length=32,
        values_callable=lambda x: [i.value for i in x],
    )


# --------------------------------------------------------------------------
# Mixins
# --------------------------------------------------------------------------


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    # M5: JWT auth — PBKDF2 hash, nullable so pre-auth rows keep working
    # until their owner sets a password via signup.
    password_hash: Mapped[str | None] = mapped_column(String(300), nullable=True)
    plan: Mapped[PlanTier] = mapped_column(_enum(PlanTier), default=PlanTier.FREE)
    theme_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # M8-C3 (migration 0009_m8c3): admin + suspension controls
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    suspended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    suspended_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # M8-C5 (migration 0011_m8c5): 7-step onboarding state
    onboarding_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Feature 1 (migration 0015_email_verification): signup email verification.
    #
    # server_default="0" (not just `default=False`) is deliberate. `default` is
    # applied by Python on INSERT; rows written by anything that is not this
    # ORM — a migration backfill, a psql session, a future bulk import — would
    # get NULL, and `not None` is falsy, so those users would be locked out by
    # the get_current_user gate. The server default makes the database itself
    # answer the question.
    #
    # Pre-existing rows are backfilled to TRUE by migration 0015: they signed
    # up before this feature existed and must not be locked out of an account
    # they already own. Only signups from 0015 onward start FALSE.
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    products: Mapped[list["Product"]] = relationship(back_populates="user")
    email_verification_tokens: Mapped[list["EmailVerificationToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tutorial_progress: Mapped[list["TutorialProgress"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    chat_sessions: Mapped[list["ChatSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    support_tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class ChatSession(TimestampMixin, Base):
    """One support-chat conversation (Feature 3).

    Sessions exist so a follow-up like "what about the second one?" has
    something to resolve against, and so "start a new chat" can mean something
    other than deleting history.

    RETENTION: purged after SUPPORT_CHAT_RETENTION_DAYS by
    app/workers/support_tasks.py, keyed on last_message_at rather than
    created_at -- an old session someone is still using is not stale, and
    deleting a live conversation out from under a user is worse than keeping it
    a few days longer.
    """

    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan",
        order_by="ChatMessage.seq",
    )
    # NO delete cascade -- deleting a session must NULL the tickets that
    # reference it, never delete them. The database says the same thing via
    # ON DELETE SET NULL, but SQLite only enforces FK actions with
    # PRAGMA foreign_keys=ON (off in the unit-test harness), so without this
    # relationship the ORM left a dangling session id behind on SQLite and
    # the two databases disagreed. Declaring it here makes the ORM null the
    # column itself, identically everywhere.
    tickets: Mapped[list["SupportTicket"]] = relationship(
        back_populates="chat_session"
    )


class ChatMessage(Base):
    """One turn in a support chat.

    `role` is 'user' or 'assistant'. Both are stored: an assistant reply that
    cannot be read back is a reply nobody can audit, and the whole point of
    grounding the bot is being able to answer "why did it say that?".

    The diagnostic columns exist for exactly that question:
      reason      why the user got this text (answered / off_topic /
                  low_confidence / model_error / malformed_response ...)
      confidence  what the model claimed about itself
      faq_ids     which knowledge-base entries were actually cited, filtered
                  to ids that really exist so a hallucinated citation is never
                  stored as a real one

    NO TimestampMixin: a chat message is immutable once written, so an
    updated_at column would only ever record that something went wrong.
    """

    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True,
        nullable=False,
    )
    # Position within the conversation, 0-based.
    #
    # Ordering by created_at ALONE is not safe: both turns of one exchange are
    # written inside a single request and can land on the same timestamp, at
    # which point the tiebreak was a random UUID primary key -- so a transcript
    # could come back with the answer before the question. It failed
    # intermittently, which is exactly how an ordering bug reaches production.
    #
    # Message order within a conversation is a real domain concept, so it gets
    # a real column rather than depending on clock resolution.
    seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0",
                                     nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Assistant messages only; NULL on user turns.
    reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    faq_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    suggest_ticket: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True,
        nullable=False,
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class SupportTicket(TimestampMixin, Base):
    """A question the AI could not answer, escalated to a human.

    Stored in the database and NOT emailed. Email delivery is deferred with the
    rest of Feature 1's transport work -- and a ticket that is only emailed is
    a ticket that is lost when the relay is down, so storing it is the durable
    half regardless of whether mail is ever added on top.

    `chat_session_id` is nullable and ON DELETE SET NULL: a ticket must outlive
    the 30-day chat purge. Losing the conversation that produced a ticket is
    acceptable; losing the ticket is not.
    """

    __tablename__ = "support_tickets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chat_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="open", server_default="open", index=True,
        nullable=False,
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship(back_populates="support_tickets")
    chat_session: Mapped["ChatSession | None"] = relationship(
        back_populates="tickets"
    )


class TutorialCatalogue(TimestampMixin, Base):
    """One tutorial video (Task 3, migration 0018).

    MOVED HERE FROM CODE. Feature 2 kept the catalogue in
    app/services/tutorials.py so that swapping a placeholder id was a reviewed
    one-line diff. That decision was reversed deliberately: adding a video now
    happens in the admin UI, with no deploy. app/services/tutorials.py keeps
    the same nine entries as SEED_CATALOGUE -- migration 0018 inserts them and
    nothing reads them at runtime.

    `slug` is still the permanent identifier. tutorial_progress rows point at
    it by string, so RENAMING A SLUG STILL ORPHANS every user's progress for
    that video -- moving the catalogue into a table did not change that, and
    deliberately did NOT add a foreign key: an FK added retroactively fails on
    any progress row whose tutorial was deleted, and progress outliving a
    deleted tutorial is the behaviour we want (undelete restores it).

    is_published defaults FALSE. A tutorial with no youtube_id would otherwise
    appear to users as a permanent "coming soon" card, which is worse than not
    appearing at all -- the Learn tab looks broken rather than short.
    """

    __tablename__ = "tutorial_catalogue"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True,
                                      nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    level: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    # NULL until a real video exists. Not an empty string and not a fake id:
    # a fake id renders YouTube's own "Video unavailable" error, which looks
    # exactly like a bug in this app.
    youtube_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0,
                                            server_default="0", nullable=False)
    is_published: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", index=True, nullable=False
    )


class TutorialProgress(TimestampMixin, Base):
    """One user's progress through one tutorial video (Feature 2).

    The video CATALOGUE is not in the database -- it lives in
    app/services/tutorials.py, and this table references it by `tutorial_slug`.
    See that module's docstring for why. The practical consequence is that a
    slug is a permanent identifier: RENAMING ONE ORPHANS every progress row
    pointing at it. Titles can change freely; slugs cannot.

    There is deliberately NO foreign key to a tutorials table, because there is
    no such table. The API validates the slug against the catalogue before
    writing, so an unknown slug is a 404 rather than a silently-stored orphan.

    UNIQUE (user_id, tutorial_slug): one row per user per video. Without it a
    client that fires two progress updates in quick succession -- which a video
    player does constantly -- creates duplicate rows, and "have I finished
    this?" stops having a single answer.

    WHY percent AND position_seconds BOTH EXIST, AND WHY THEY UPDATE
    DIFFERENTLY:
      position_seconds is "where do I resume", so it takes the LATEST value --
        a user who scrubs back to the start expects to resume at the start.
      percent is "how much of this have I seen", so it takes the MAXIMUM --
        scrubbing back must not erase what has already been watched, or a
        rewatch would undo a completion.
    Storing only one of them cannot express both behaviours.
    """

    __tablename__ = "tutorial_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "tutorial_slug",
                         name="uq_tutorial_progress_user_id_tutorial_slug"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    tutorial_slug: Mapped[str] = mapped_column(String(100), index=True,
                                               nullable=False)
    # Resume point, in seconds. Latest value wins.
    position_seconds: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    # Reported by the player; nullable because the catalogue may not know it
    # and the player has not loaded yet on the first update.
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Furthest point reached, 0-100. Monotonic; only a reset lowers it.
    percent: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0", nullable=False
    )
    completed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_watched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="tutorial_progress")


class EmailVerificationToken(Base):
    """One outstanding signup-verification link.

    THE RAW TOKEN IS NEVER STORED. Only sha256(token) is, in `token_hash`.
    A verification link is a bearer credential — anyone holding it can mark an
    account verified — so a leaked database dump must not hand an attacker a
    working link for every pending signup. The raw value exists exactly twice:
    in the email, and in the query string of the click. Lookup is by hash.

    Single use: `used_at` is stamped on the first successful click, and the
    verify endpoint refuses a token that already has one. Without that, a
    forwarded email or a mail-scanner prefetch keeps re-verifying an account
    the user may since have had suspended.

    Rows are kept after use rather than deleted, so "this link was already
    used" is distinguishable from "this link never existed" — the difference
    between a helpful message and a confusing one.
    """

    __tablename__ = "email_verification_tokens"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # sha256 hex digest of the raw token — 64 chars, unique so a hash
    # collision or a duplicated insert surfaces as an error, not a silent
    # second live link for the same value.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True,
                                            nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="email_verification_tokens")


class Product(TimestampMixin, Base):
    """A product OR a skill the user wants clients for."""

    __tablename__ = "products"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    type: Mapped[ProductType] = mapped_column(_enum(ProductType))

    user: Mapped["User"] = relationship(back_populates="products")
    past_clients: Mapped[list["PastClient"]] = relationship(back_populates="product")
    strategies: Mapped[list["Strategy"]] = relationship(back_populates="product")


class PastClient(TimestampMixin, Base):
    """Flow 1 input: one past client + how they were acquired."""

    __tablename__ = "past_clients"

    id: Mapped[uuid.UUID] = _uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    details: Mapped[str] = mapped_column(Text)
    acquisition_story: Mapped[str] = mapped_column(Text)
    # Filled by the Chunk 3 pattern-recognition service (Claude):
    # industry, company_size, buyer_role, deal_size, channel,
    # trigger_event, sales_cycle_length.
    extracted_patterns_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    product: Mapped["Product"] = relationship(back_populates="past_clients")


class Strategy(TimestampMixin, Base):
    __tablename__ = "strategies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    flow_type: Mapped[FlowType] = mapped_column(_enum(FlowType))
    status: Mapped[StrategyStatus] = mapped_column(
        _enum(StrategyStatus), default=StrategyStatus.PENDING, index=True
    )
    # Chunk 5 verification loop appends one entry per pass attempt:
    # {pass_no, name, attempt, result: PASS|FAIL, fix_description?, ts}
    verified_passes_json: Mapped[list] = mapped_column(JSON, default=list)
    # Assembled final strategy document (written when pipeline completes).
    strategy_document: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Flow 2 only: assembled GTM document.
    gtm_document: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Outreach campaign state (M3): "active" | "paused_bounce_rate" | "paused_manual"
    campaign_state: Mapped[str] = mapped_column(String(30), default="active")
    campaign_pause_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # M8-C1 (migration 0008_m8c2): SHA-256 of sorted canonical ICP/tactic JSON —
    # links a strategy to its playbook_scores rows (O(1) upsert key).
    pattern_key: Mapped[str | None] = mapped_column(
        String(200), nullable=True, index=True
    )
    # 0014: the exact canonical dict that was hashed into pattern_key. Stored
    # so the bucket is auditable and so a recompute/backfill can rehash offline
    # instead of re-asking the model for the ICP and tactic profile (which is
    # not deterministic across runs, and would silently re-bucket a strategy
    # that never changed). See icp_extraction.canonical_pattern_payload.
    pattern_inputs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # M8-C2: winning variant set by auto-promotion. Affects FUTURE message
    # rendering only — in-flight rows (sent_at IS NOT NULL) are never touched.
    default_variant: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # M8-C4 (migration 0010_m8c4): Pearson correlation between message
    # personalization score and reply outcome, computed nightly.
    personalization_correlation: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )

    product: Mapped["Product"] = relationship(back_populates="strategies")
    research_steps: Mapped[list["ResearchStep"]] = relationship(
        back_populates="strategy"
    )
    leads: Mapped[list["Lead"]] = relationship(back_populates="strategy")
    sequences: Mapped[list["Sequence"]] = relationship(back_populates="strategy")


class ResearchStep(TimestampMixin, Base):
    """One persisted pipeline step output.

    The UNIQUE constraint below is the resumability guarantee from the
    project knowledge: a crashed run resumes from the last saved step and
    can never insert the same step twice.
    """

    __tablename__ = "research_steps"
    __table_args__ = (
        UniqueConstraint("strategy_id", "pipeline", "step_no", name="strategy_pipeline_step"),
        Index("ix_research_steps_strategy_phase", "strategy_id", "pipeline", "phase"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    pipeline: Mapped[PipelineKind] = mapped_column(
        _enum(PipelineKind), default=PipelineKind.STRATEGY
    )
    phase: Mapped[int] = mapped_column(Integer)      # 1..8
    step_no: Mapped[int] = mapped_column(Integer)    # 1..72 within the pipeline
    step_id: Mapped[str] = mapped_column(String(64))  # registry id, e.g. "s1.03"
    name: Mapped[str] = mapped_column(String(200))
    inputs_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(64))

    strategy: Mapped["Strategy"] = relationship(back_populates="research_steps")


class LeadBatch(TimestampMixin, Base):
    """One sourcing run for a strategy: source -> enrich -> find emails ->
    verify -> finalize. Stage + per-lead statuses make the whole chain
    resumable, consistent with the M1 engine's resumability rule."""

    __tablename__ = "lead_batches"

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    stage: Mapped[BatchStage] = mapped_column(
        _enum(BatchStage), default=BatchStage.SOURCING, index=True
    )
    requested_leads: Mapped[int] = mapped_column(Integer)
    icp_criteria_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_provider: Mapped[str] = mapped_column(String(50), default="apollo")
    verifier_provider: Mapped[str] = mapped_column(String(50), default="hunter")
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    leads: Mapped[list["Lead"]] = relationship(back_populates="batch")


class Lead(TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (
        # M2 dedupe rule, enforced by the schema: same email or same
        # provider person-id can only exist once per strategy.
        UniqueConstraint("strategy_id", "email", name="strategy_email"),
        UniqueConstraint("strategy_id", "source", "external_id", name="strategy_source_external"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead_batches.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(50))  # "apollo", "manual", ...
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    company: Mapped[str | None] = mapped_column(String(200), nullable=True)
    enrichment_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[LeadStatus] = mapped_column(
        _enum(LeadStatus), default=LeadStatus.SOURCED, index=True
    )
    # --- WhatsApp channel (M4) -------------------------------------------
    # Opt-in is a compliance fact: recorded with WHEN and HOW (source), and
    # required by the adapter before ANY outbound WhatsApp message. Full
    # opt-in collection flows land in Chunk 2; the fields exist from Chunk 1
    # so the send-time guard is structural, never retrofitted.
    whatsapp_opted_in: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    whatsapp_opt_in_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    whatsapp_opt_in_source: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Timestamp of the last INBOUND WhatsApp message from this lead —
    # persisted by the webhook since Chunk 1; Chunk 3's 24h customer-service
    # window check reads it.
    whatsapp_last_inbound_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    strategy: Mapped["Strategy"] = relationship(back_populates="leads")
    batch: Mapped["LeadBatch | None"] = relationship(back_populates="leads")
    messages: Mapped[list["Message"]] = relationship(back_populates="lead")
    outcomes: Mapped[list["Outcome"]] = relationship(back_populates="lead")


class Sequence(TimestampMixin, Base):
    """An outreach sequence (a named cadence of messages on one channel)."""

    __tablename__ = "sequences"

    id: Mapped[uuid.UUID] = _uuid_pk()
    strategy_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("strategies.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[ChannelType] = mapped_column(_enum(ChannelType))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[SequenceStatus] = mapped_column(
        _enum(SequenceStatus), default=SequenceStatus.DRAFT
    )
    booking_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    strategy: Mapped["Strategy"] = relationship(back_populates="sequences")
    steps: Mapped[list["SequenceStep"]] = relationship(
        back_populates="sequence", order_by="SequenceStep.step_no"
    )
    enrollments: Mapped[list["SequenceEnrollment"]] = relationship(back_populates="sequence")
    messages: Mapped[list["Message"]] = relationship(back_populates="sequence")


class SequenceStep(TimestampMixin, Base):
    """One ordered step of a sequence. `template` is the messaging brief
    Claude personalizes per lead (not the final copy). `delay_days` is the
    wait after the PREVIOUS step's send."""

    __tablename__ = "sequence_steps"
    __table_args__ = (
        UniqueConstraint("sequence_id", "step_no", name="sequence_step"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sequences.id", ondelete="CASCADE"), index=True
    )
    step_no: Mapped[int] = mapped_column(Integer)          # 1 = initial email
    template: Mapped[str] = mapped_column(Text)
    variant: Mapped[str] = mapped_column(String(20), default="A")
    delay_days: Mapped[int] = mapped_column(Integer, default=3)
    # --- M4 Chunk 3: multi-channel sequences -----------------------------
    # NULL channel = "use the sequence's channel" — every M3 sequence keeps
    # working unchanged. A non-null value overrides per step (e.g. step 1
    # email, step 3 WhatsApp template follow-up).
    channel: Mapped[ChannelType | None] = mapped_column(
        _enum(ChannelType), nullable=True
    )
    # WhatsApp-only fields (NULL for email steps):
    whatsapp_kind: Mapped[WhatsAppStepKind | None] = mapped_column(
        _enum(WhatsAppStepKind), nullable=True
    )
    whatsapp_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("whatsapp_templates.id", ondelete="SET NULL"), nullable=True
    )
    # {"1": "lead.full_name", "2": "brief: their biggest onboarding pain"}
    # — 'lead.<field>' fills deterministically; anything else is a brief
    # Claude fills from lead enrichment + strategy messaging.
    variable_mapping_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # --- Engagement Hub: automated follow-up (migration 0020) -------------
    # `delay_days` schedules the NEXT step after this one SENDS. These two
    # govern something different: what happens when the lead does not reply
    # to this step at all. The sweep in app/workers/outreach_tasks.py
    # (check_followup_due) reads them per step.
    #
    # Both carry a server_default as well as a Python default because
    # migration 0020 adds them to a table that already has rows: without one
    # the ALTER cannot make the column NOT NULL, and a NULL delay would make
    # the sweep's arithmetic silently skip every pre-existing step.
    followup_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    followup_delay_hours: Mapped[int] = mapped_column(
        Integer, default=72, server_default=text("72"), nullable=False
    )

    sequence: Mapped["Sequence"] = relationship(back_populates="steps")

    def effective_channel(self, sequence: "Sequence") -> ChannelType:
        return self.channel or sequence.channel


class SequenceEnrollment(TimestampMixin, Base):
    """Per-(sequence, lead) state. Hard stop conditions set status=STOPPED
    with a reason; the engine refuses to send for stopped enrollments —
    templates never see or control this."""

    __tablename__ = "sequence_enrollments"
    __table_args__ = (
        UniqueConstraint("sequence_id", "lead_id", name="sequence_lead"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sequences.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        _enum(EnrollmentStatus), default=EnrollmentStatus.ACTIVE, index=True
    )
    stop_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    paused_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0)

    sequence: Mapped["Sequence"] = relationship(back_populates="enrollments")
    lead: Mapped["Lead"] = relationship()


class Message(TimestampMixin, Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = _uuid_pk()
    sequence_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sequences.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[ChannelType] = mapped_column(_enum(ChannelType))
    step_no: Mapped[int] = mapped_column(Integer, default=1)
    template: Mapped[str] = mapped_column(Text)                     # step brief snapshot
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)   # final rendered body, persisted BEFORE send
    variant: Mapped[str] = mapped_column(String(20), default="A")  # A/B testing
    # M4 Chunk 3: how a WhatsApp message sends + which template row it uses
    # (snapshot at scheduling time; NULL for email messages).
    whatsapp_kind: Mapped[WhatsAppStepKind | None] = mapped_column(
        _enum(WhatsAppStepKind), nullable=True
    )
    whatsapp_template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("whatsapp_templates.id", ondelete="SET NULL"), nullable=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    thread_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unsubscribe_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)  # gmail account id
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[MessageStatus] = mapped_column(
        _enum(MessageStatus), default=MessageStatus.SCHEDULED
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # M8-C4 (migration 0010_m8c4): field-presence personalization score
    # computed at send time (0.0–1.0).
    personalization_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    sequence: Mapped["Sequence"] = relationship(back_populates="messages")
    lead: Mapped["Lead"] = relationship(back_populates="messages")


class Outcome(Base):
    """Immutable event log feeding the M8 learning loop. No updated_at."""

    __tablename__ = "outcomes"
    __table_args__ = (Index("ix_outcomes_lead_event", "lead_id", "event"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    # 0012: nullable — outcomes also audits system-level events
    # (ab_promoted, circuit_opened) which have a strategy but no lead.
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True, nullable=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    # M8-C1 (migration 0008_m8c2): denormalized learning-loop dimensions.
    # strategy_id lets the nightly aggregation and A/B sweep GROUP BY strategy
    # without a 3-table join; variant snapshots the message variant at event
    # time (messages can be re-variant-ed later; outcomes are immutable).
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    variant: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    event: Mapped[OutcomeEvent] = mapped_column(_enum(OutcomeEvent))
    # M4 Chunk 3: the channel this event happened on — a REAL, queryable
    # column (not buried in meta_json) because M8's learning loop compares
    # channel performance. 'system' for channel-less events (GDPR delete).
    channel: Mapped[str] = mapped_column(String(20), default="email",
                                         nullable=False, index=True)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lead: Mapped["Lead"] = relationship(back_populates="outcomes")


class PlaybookScore(TimestampMixin, Base):
    """Learned effectiveness of a tactic, aggregated nightly (M8).

    M8-C1 (migration 0008_m8c2) reshapes this from the M1 (pattern_key, metric)
    scalar rows into per-variant rows carrying both rates, keyed on
    (pattern_key, variant) — the upsert key used by the nightly aggregation.
    `metric` is kept nullable for backwards compatibility with M1 rows.
    """

    __tablename__ = "playbook_scores"
    __table_args__ = (
        UniqueConstraint("pattern_key", "variant", name="pattern_variant"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    pattern_key: Mapped[str] = mapped_column(String(200), index=True)
    metric: Mapped[str | None] = mapped_column(String(50), nullable=True)  # legacy M1
    variant: Mapped[str] = mapped_column(String(20), default="A", nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    reply_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    booking_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    is_reliable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_aggregated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # M8-C4 (migration 0010_m8c4): exponential score decay metadata
    effective_sample_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    decay_half_life_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    oldest_outcome_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trend: Mapped[str | None] = mapped_column(String(20), nullable=True)  # new/rising/falling/stable


class GmailAccount(TimestampMixin, Base):
    """A user's connected Gmail account. OAuth tokens are stored ONLY as
    Fernet ciphertext (app/services/crypto.py) — encrypted at rest.
    token_expires_at is duplicated in plaintext purely so the refresh
    check does not need a decrypt; it is not sensitive."""

    __tablename__ = "gmail_accounts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True
    )
    email_address: Mapped[str | None] = mapped_column(String(320), nullable=True)
    token_ciphertext: Mapped[str] = mapped_column(Text)  # encrypted JSON token set
    token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[str] = mapped_column(String(500), default="")
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SuppressionEntry(Base):
    """Contacts who must NEVER be messaged again. Checked at sourcing time
    (M2) and again before every send (M3+). Compliance rule, no exceptions."""

    __tablename__ = "suppression_list"
    __table_args__ = (
        CheckConstraint(
            "(email IS NOT NULL) OR (phone IS NOT NULL)",
            name="email_or_phone_present",
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str | None] = mapped_column(
        String(320), nullable=True, unique=True, index=True
    )
    phone: Mapped[str | None] = mapped_column(
        String(50), nullable=True, unique=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(200))  # unsubscribed, gdpr_delete...
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InboundReply(TimestampMixin, Base):
    """An inbound message matched (or attempted) to a lead, with its
    classification. Stored for the user to act on — LeadPilot never
    auto-replies to humans in M3."""

    __tablename__ = "inbound_replies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=True, index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True
    )
    account_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # M4 Chunk 3: which channel this inbound arrived on.
    channel: Mapped[str] = mapped_column(String(20), default="email",
                                         nullable=False, index=True)
    thread_ref: Mapped[str | None] = mapped_column(String(128), nullable=True)
    from_address: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body: Mapped[str] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(40), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WhatsAppTemplate(TimestampMixin, Base):
    """A Meta message template. Chunk 2 lifecycle:
        draft -> submitted -> approved | rejected (+ rejection_reason)
    Approved templates are IMMUTABLE in our db — an edit creates a new
    row with version+1 and supersedes_id pointing at the old one (Meta
    also versions templates under the same name). Only status=approved
    templates are ever sendable — enforced in the adapter's send() guard."""

    __tablename__ = "whatsapp_templates"
    __table_args__ = (
        # Meta identifies templates by (name, language); we add version so
        # edits of approved templates can create a new draft under the
        # same identity.
        UniqueConstraint("name", "language", "version",
                         name="template_name_language_version"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), index=True)
    language: Mapped[str] = mapped_column(String(20))  # e.g. "en_US"
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    category: Mapped[WhatsAppTemplateCategory] = mapped_column(
        _enum(WhatsAppTemplateCategory),
        default=WhatsAppTemplateCategory.MARKETING,
    )
    status: Mapped[WhatsAppTemplateStatus] = mapped_column(
        _enum(WhatsAppTemplateStatus), default=WhatsAppTemplateStatus.DRAFT
    )
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {"1": "prospect first name", "2": "their company", ...} — tells the
    # sequence engine (Chunk 3) what each {{n}} placeholder means.
    variable_descriptions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Meta's own template id, filled on submit/sync.
    meta_template_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("whatsapp_templates.id", ondelete="SET NULL"), nullable=True
    )


class WhatsAppOptIn(Base):
    """APPEND-ONLY audit trail of WhatsApp consent events per lead.

    Opt-in is a compliance fact, not a boolean: every row records WHO
    (lead + phone), WHAT (opted_in/opted_out), HOW (source), the EVIDENCE
    (URL / message id / import note) and the exact consent text shown.
    Rows are never updated or deleted — a revocation is a NEW opted_out
    row. The lead's current status is the latest row; Lead.whatsapp_opted_in
    is only a denormalized cache of that, maintained by
    app/services/whatsapp_optin.py."""

    __tablename__ = "whatsapp_optins"

    id: Mapped[uuid.UUID] = _uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    phone: Mapped[str] = mapped_column(String(20))  # normalized E.164 (+digits)
    status: Mapped[OptInStatus] = mapped_column(_enum(OptInStatus))
    source: Mapped[OptInSource] = mapped_column(_enum(OptInSource))
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    consent_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProcessedWebhook(Base):
    """Idempotency ledger for webhook deliveries (Calendly/WhatsApp retries)."""

    __tablename__ = "processed_webhooks"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="provider_event"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(40))
    event_id: Mapped[str] = mapped_column(String(200))
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

# --------------------------------------------------------------------------
# M7 — mobile push notifications
# --------------------------------------------------------------------------


class DeviceToken(TimestampMixin, Base):
    """FCM device token registered by the mobile app (M7 Chunk 3).

    Upsert semantics: (user_id, token) unique — re-registering the same token
    updates the row instead of duplicating it.
    """

    __tablename__ = "device_tokens"
    __table_args__ = (
        # Globally unique on token alone, matching devices.py's
        # ON CONFLICT (token) upsert and its documented token-transfer
        # behaviour. An FCM registration token identifies one app install, so
        # two accounts must not both hold a row for the same physical device.
        # See migration 0013_device_token_unique.
        UniqueConstraint("token", name="uq_device_tokens_token"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token: Mapped[str] = mapped_column(String(512), nullable=False)
    platform: Mapped[str] = mapped_column(String(20), default="android")
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# --------------------------------------------------------------------------
# M8-C1/C3 — encrypted provider tokens (migrations 0008_m8c2 + 0009_m8c3)
# --------------------------------------------------------------------------


class IntegrationToken(TimestampMixin, Base):
    """Provider credentials at rest (Apollo/Hunter/Gmail/WhatsApp/Calendly).

    Written by app.integrations.token_store.TokenStore — values are stored in
    `encrypted_value` (Fernet, migration 0009_m8c3); the plaintext `value`
    column exists only for the 0009 backfill and is nulled by it.
    """

    __tablename__ = "integration_tokens"
    __table_args__ = (
        UniqueConstraint("user_id", "provider", "token_kind", name="user_provider_kind"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(40), index=True)   # apollo, hunter, gmail...
    token_kind: Mapped[str] = mapped_column(String(40), default="api_key")
    value: Mapped[str | None] = mapped_column(Text, nullable=True)  # legacy plaintext (backfilled → NULL)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # encrypted_value column is ADDED by migration 0009_m8c3
    encrypted_value: Mapped[str | None] = mapped_column(Text, nullable=True)


# --------------------------------------------------------------------------
# M8-C4 — subject line intelligence (migration 0010_m8c4)
# --------------------------------------------------------------------------


class SubjectLinePattern(Base):
    """Aggregated performance of a subject-line pattern class per channel."""

    __tablename__ = "subject_line_patterns"
    __table_args__ = (
        UniqueConstraint("pattern_type", "channel", name="pattern_channel"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    pattern_type: Mapped[str] = mapped_column(String(50), index=True)
    channel: Mapped[str] = mapped_column(String(20), default="gmail")
    example: Mapped[str | None] = mapped_column(String(500), nullable=True)
    avg_reply_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_meeting_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    is_reliable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False
    )


# --------------------------------------------------------------------------
# M8-C5 — reliable outbound webhooks (migration 0011_m8c5)
# --------------------------------------------------------------------------


class WebhookTarget(TimestampMixin, Base):
    """A user-registered outbound webhook destination (HMAC-signed deliveries)."""

    __tablename__ = "webhook_targets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    event_types: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)


class WebhookDelivery(Base):
    """Delivery log for outbound webhooks — 5-retry exponential backoff."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[uuid.UUID] = _uuid_pk()
    target_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("webhook_targets.id", ondelete="CASCADE"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(60), index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# --------------------------------------------------------------------------
# M9 — native CRM layer (migration 0019_m9_crm)
# --------------------------------------------------------------------------
#
# Design note that governs this whole block: NOT ONE existing table is
# modified. `leads`, `strategies` and `outcomes` are read by M1–M8 code
# paths (the sourcing chain, the sequence engine, the nightly learning
# loop) and by the published SDK; adding a column to `leads` for the CRM's
# owner field or its custom-field bag would put M9's UI concerns inside the
# row every one of those reads. So CRM-only per-lead state lives in
# `crm_lead_meta`, and user-defined fields live in a definition + value pair
# — both joined on lead_id, both droppable without touching the lead.


class CrmNote(TimestampMixin, Base):
    """A free-text note a user wrote on a lead.

    Editable (updated_at moves) but `created_at` is never rewritten — the
    activity feed orders by when the note was WRITTEN, and letting an edit
    jump a three-week-old note to the top of the timeline would make the
    feed lie about the sequence of events.
    """

    __tablename__ = "crm_notes"
    __table_args__ = (
        Index("ix_crm_notes_lead_created", "lead_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    # The note's author. SET NULL rather than CASCADE: deleting a user must
    # not silently erase the notes that are still attached to a live lead.
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body: Mapped[str] = mapped_column(Text)

    lead: Mapped["Lead"] = relationship()


class CrmActivity(Base):
    """Append-only, UI-facing audit trail per lead. No updated_at.

    This is NOT `outcomes`. `outcomes` is the M8 learning loop's immutable
    event log: the nightly aggregation, the A/B sweep and the playbook
    scorer all read it, filtered by strategy_id/variant/channel, and it is
    deliberately narrow. Writing "note added" or "tag removed" rows into it
    would put UI noise inside every one of those aggregates and change the
    denominators the learning loop computes its rates from.

    `actor_user_id` is NULL for machine-generated activity (the sourcing
    chain, a webhook), which is how the feed distinguishes "you moved this"
    from "the pipeline moved this".
    """

    __tablename__ = "crm_activities"
    __table_args__ = (
        Index("ix_crm_activities_lead_ts", "lead_id", "ts"),
        # The account-wide feed (dashboard page 4) orders by ts across every
        # lead the user owns; without this it is a full scan + filesort once
        # the table has real volume.
        Index("ix_crm_activities_strategy_ts", "strategy_id", "ts"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    # Denormalized from lead.strategy_id for the same reason
    # outcomes.strategy_id is denormalized: the account-wide feed filters by
    # strategy and would otherwise need a join on every page.
    strategy_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("strategies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[CrmActivityKind] = mapped_column(_enum(CrmActivityKind), index=True)
    # Human-readable before/after for status and field changes. Stored as
    # text, not as foreign keys: an activity row must stay readable after
    # whatever it references has been renamed or deleted.
    from_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meta_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # BOTH defaults, and the Python one is load-bearing.
    #
    # For this table ordering IS the feature -- it is a timeline, read newest
    # first -- and `func.now()` alone cannot order it. On SQLite
    # CURRENT_TIMESTAMP has one-second resolution, so every event in the same
    # second ties; on PostgreSQL now() is transaction-scoped, so every row
    # written by one request ties by construction. Ties fall through to the
    # `id DESC` tiebreaker, which on a random UUID4 is stable but meaningless
    # -- the feed would show two events in the correct order only by luck, and
    # the keyset cursor would skip or repeat across a tied group.
    #
    # A Python-side default is evaluated once per row at insert, in
    # microseconds, and is not transaction-scoped, so it actually orders. The
    # server_default stays as the backstop for a row written by anything that
    # is not this ORM (a migration backfill, a psql session), same reasoning
    # as users.email_verified.
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    lead: Mapped["Lead"] = relationship()


class CrmTag(TimestampMixin, Base):
    """A user-defined label. Scoped per user, not per strategy, so one tag
    ("warm intro", "budget confirmed") is reusable across every campaign.

    `color_token` names a THEME TOKEN (primary / accent / success / warning /
    destructive / muted), never a hex value. The theme engine recolors the
    whole app from CSS variables; a tag storing #16a34a would be the one
    thing on screen that ignores the user's chosen preset.
    """

    __tablename__ = "crm_tags"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="crm_tag_user_name"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(60))
    color_token: Mapped[str] = mapped_column(
        String(20), default="muted", server_default="muted", nullable=False
    )


class CrmLeadTag(Base):
    """lead to tag association. The unique constraint makes double-tagging
    impossible at the schema level, so the bulk-tag endpoint can be naively
    idempotent instead of reading before every write."""

    __tablename__ = "crm_lead_tags"
    __table_args__ = (
        UniqueConstraint("lead_id", "tag_id", name="crm_lead_tag_unique"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_tags.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CrmSavedView(TimestampMixin, Base):
    """A named filters+sort+columns combination, persisted SERVER-side.

    localStorage was the cheaper option and the wrong one: a saved view is
    the user's own work (they built the filter set), and putting it in
    browser storage means it is invisible on their phone, gone when they
    clear site data, and unrecoverable when they switch machines.

    `is_default` is kept unique per (user, view_type) by the service layer
    rather than by a partial unique index — SQLite and PostgreSQL both
    support partial indexes, but their syntax diverges enough that the
    constraint would need two dialect branches in the migration to express a
    rule that is one UPDATE at the call site.
    """

    __tablename__ = "crm_saved_views"
    __table_args__ = (
        UniqueConstraint("user_id", "view_type", "name",
                         name="crm_view_user_type_name"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    view_type: Mapped[CrmViewType] = mapped_column(
        _enum(CrmViewType), default=CrmViewType.GRID, index=True
    )
    filters_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sort_json: Mapped[list] = mapped_column(JSON, default=list)
    # [{key, width, visible, order}] — column WIDTHS live here too, so a
    # view restores the exact layout, not just the data selection.
    columns_json: Mapped[list] = mapped_column(JSON, default=list)
    is_default: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="0", nullable=False
    )


class CrmCustomField(TimestampMixin, Base):
    """Definition of a user-defined column on the grid.

    `key` is the stable machine name a saved view's columns_json references;
    `label` is what the header shows. They are separate so that renaming a
    field does not orphan every saved view that displays it.
    """

    __tablename__ = "crm_custom_fields"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="crm_field_user_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(60))
    label: Mapped[str] = mapped_column(String(100))
    field_type: Mapped[CrmFieldType] = mapped_column(
        _enum(CrmFieldType), default=CrmFieldType.TEXT
    )
    # SELECT only: the allowed choices. Validated on write, so a value that
    # is not in this list can never be stored.
    options_json: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )


class CrmCustomFieldValue(TimestampMixin, Base):
    """One field's value for one lead (EAV).

    WHY EAV RATHER THAN A JSON BAG ON `leads`:
      1. A JSON column on `leads` is a schema change to a table that M1–M8
         and the published SDK all read. This table is additive, and it can
         be dropped without touching a lead row.
      2. The grid sorts and filters on custom fields SERVER-side, across
         5,000+ rows. JSON extraction is spelled differently in SQLite
         (json_extract) and PostgreSQL (->>), with different NULL and
         collation behaviour, so the test suite would exercise a different
         query than production runs. A plain indexed column does not have
         that problem.

    THE COST, stated plainly: reading N leads with their custom values is
    two queries, not one. The grid endpoint issues exactly one extra
    `WHERE lead_id IN (...)` for the page's <=200 ids and assembles the rows
    in Python — bounded, not N+1.

    `value_text` is the canonical sortable/filterable form and is ALWAYS
    populated (numbers zero-padded, dates ISO-8601, bools "true"/"false") so
    that lexical ordering matches semantic ordering. `value_json` carries the
    typed original so a round-trip never loses precision.
    """

    __tablename__ = "crm_custom_field_values"
    __table_args__ = (
        UniqueConstraint("field_id", "lead_id", name="crm_field_value_unique"),
        Index("ix_crm_field_values_field_text", "field_id", "value_text"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    field_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crm_custom_fields.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    value_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class CrmLeadMeta(TimestampMixin, Base):
    """CRM-only per-lead state — the columns that would otherwise have been
    added to `leads`.

    `stage_entered_at` earns this table on its own. Lead velocity ("how long
    has this one been sitting in contacted?") needs the moment the CURRENT
    status was entered, and nothing in M1–M8 records it: `leads.updated_at`
    moves on any write at all, including a WhatsApp opt-in timestamp that
    says nothing about the stage. Leads that last changed status before M9
    shipped have no meta row; the dashboard falls back to `leads.updated_at`
    for those and labels the figure estimated, rather than quietly averaging
    two different measurements together.
    """

    __tablename__ = "crm_lead_meta"
    __table_args__ = (
        UniqueConstraint("lead_id", name="crm_lead_meta_lead"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    next_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    stage_entered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    lead: Mapped["Lead"] = relationship()


# --------------------------------------------------------------------------
# Engagement Hub — self-built calendar (migration 0021)
# --------------------------------------------------------------------------
#
# WHY THIS IS NOT CALENDLY
# app/integrations/calendly.py stays exactly where it is: an account that
# already runs on Calendly keeps its links, its webhook and its bookings. The
# tables below are the OWNED path — availability the user edits in-app, a
# public booking page on our own domain, and bookings that land in the same
# database as the lead they belong to. That last part is the point: a Calendly
# booking arrives as a webhook that has to be matched back to a lead by a
# tagged UTM parameter (see calendly.py's tenant-tagging note for how fragile
# that is), whereas a booking made here already knows which page it came from
# and therefore which user owns it.
#
# TABLE NAMES: the brief spells these singular (calendar_booking_page). Every
# other table in this schema is plural, and a schema that is plural except in
# one corner is a trap for anyone writing a raw query, so they are pluralised
# here. The MODEL names are what application code touches, and those match the
# brief exactly.


class CalendarAvailability(TimestampMixin, Base):
    """One recurring weekly window a user is bookable in.

    Multiple rows per weekday are intended and normal — "9-12 and 14-17" is
    two rows, not one row with a hole in it, because a single row with a break
    would need a nested structure that no query can filter on.

    `timezone` lives on the ROW, not on the user: the times are wall-clock
    times in it ("I take calls at 9am Karachi time"), and storing them in UTC
    would move the user's morning by an hour twice a year. Slot generation in
    app/services/calendar_service.py converts to UTC per day, so DST is
    resolved at the day being offered rather than when the rule was written.
    """

    __tablename__ = "calendar_availability"
    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6",
                        name="calendar_availability_dow"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # 0 = Monday .. 6 = Sunday — Python's datetime.weekday(), so the slot
    # generator never has to translate between two week conventions.
    day_of_week: Mapped[int] = mapped_column(Integer)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    timezone: Mapped[str] = mapped_column(
        String(64), default="UTC", server_default="UTC", nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )


class CalendarBookingPage(TimestampMixin, Base):
    """A shareable page (/book/<slug>) that turns availability into a
    bookable offer.

    A user can have several: "30-min intro" and "60-min technical deep dive"
    are different durations, different questions and different links over the
    same underlying availability.
    """

    __tablename__ = "calendar_booking_pages"
    __table_args__ = (
        # Global, not per-user: the slug IS the public URL. Two users cannot
        # both own /book/intro-call.
        UniqueConstraint("slug", name="calendar_booking_page_slug"),
        CheckConstraint("duration_minutes IN (15, 30, 45, 60)",
                        name="calendar_booking_page_duration"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(80), index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_minutes: Mapped[int] = mapped_column(
        Integer, default=30, server_default=text("30"), nullable=False
    )
    # Padding AFTER each booking, so back-to-back calls are impossible.
    buffer_minutes: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    # NULL = unlimited. A sentinel like 0 would read as "nobody may book",
    # which is the opposite of what an unset field should mean.
    max_bookings_per_day: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    # [{"key": "budget", "label": "What is your budget?", "type": "text",
    #   "required": true}] — answers land in calendar_bookings.answers.
    custom_questions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )


class CalendarBooking(TimestampMixin, Base):
    """One booked slot.

    `slot_key` IS THE DOUBLE-BOOKING GUARD, and it is why this table has a
    column the brief does not list. Two people can load the same booking page
    and submit the same 10:00 slot in the same second; a check-then-insert in
    the handler loses that race, and a partial unique index (WHERE status <>
    'cancelled') is PostgreSQL-only, so the test suite would exercise a
    different constraint than production.

    Instead: slot_key holds the slot's UTC start while the booking is live and
    is set to NULL when it is cancelled. NULLs do not collide in a UNIQUE
    constraint on either PostgreSQL or SQLite, so the constraint blocks a
    second live booking of the same slot and still lets a cancelled slot be
    re-booked. One insert, no read, no race.
    """

    __tablename__ = "calendar_bookings"
    __table_args__ = (
        UniqueConstraint("booking_page_id", "slot_key",
                         name="calendar_booking_live_slot"),
        Index("ix_calendar_bookings_page_start", "booking_page_id", "start_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    booking_page_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("calendar_booking_pages.id", ondelete="CASCADE"), index=True
    )
    invitee_name: Mapped[str] = mapped_column(String(200))
    invitee_email: Mapped[str] = mapped_column(String(320), index=True)
    invitee_phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # The invitee's own IANA zone, captured at booking time. Confirmation
    # emails render the time in it; without it a person in Auckland gets a
    # confirmation for a time they have to convert by hand.
    invitee_timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meeting_link: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[BookingStatus] = mapped_column(
        _enum(BookingStatus), default=BookingStatus.CONFIRMED, index=True
    )
    # SET NULL, not CASCADE: deleting a lead must not erase the fact that a
    # meeting happened — the invitee's own record of it is this row.
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # See the class docstring: the UTC slot start while live, NULL once
    # cancelled. Never read by application logic — the constraint is the point.
    slot_key: Mapped[str | None] = mapped_column(String(40), nullable=True)

    booking_page: Mapped["CalendarBookingPage"] = relationship()
    lead: Mapped["Lead | None"] = relationship()


# --------------------------------------------------------------------------
# Engagement Hub — meetings (migration 0022)
# --------------------------------------------------------------------------


class Meeting(TimestampMixin, Base):
    """A call: where it happens, what was said, and what to do next.

    `booking_id` IS NULLABLE because meetings are also created by hand — the
    prospect proposed a time over email, or the call was booked before this
    feature existed. A NOT NULL booking would make the manual path impossible
    and force fake bookings to be written to satisfy the schema.

    `lead_id` is carried here as well as on the booking. It is not redundant:
    a manually created meeting has no booking to inherit it from, and Feature
    4's "Meetings" tab on a lead needs one indexed column to query rather than
    a LEFT JOIN through bookings that only resolves half the rows.

    THE TWO TIME PAIRS ARE DIFFERENT FACTS. start_at/end_at are what was
    scheduled; actual_start_at/actual_end_at are when Start/End Meeting were
    pressed. The AI summary prompt uses the actual duration, because "we
    booked 60 minutes and it ran 12" is a signal about the call, and folding
    it into the scheduled figure would erase it.
    """

    __tablename__ = "meetings"
    __table_args__ = (
        Index("ix_meetings_host_start", "host_user_id", "start_at"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    booking_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calendar_bookings.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    host_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    platform: Mapped[MeetingPlatform] = mapped_column(
        _enum(MeetingPlatform), default=MeetingPlatform.CUSTOM
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    meeting_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # The provider's own id for the event (Google Calendar eventId, Zoom
    # meeting id). Kept so a later cancel or reschedule can address the right
    # object instead of parsing it back out of the join URL.
    external_event_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[MeetingStatus] = mapped_column(
        _enum(MeetingStatus), default=MeetingStatus.SCHEDULED, index=True
    )
    # What the user typed during the call. Never overwritten by the AI —
    # ai_notes is a separate column precisely so a generated summary can never
    # destroy a human's own record of what was said.
    raw_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    recording_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    # [{"text": "...", "owner": "us"|"client", "due": "2026-09-14",
    #   "done": false}] — `done` is written back by the checkbox list in the UI.
    action_items: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # The remaining three fields of meeting_ai.generate_meeting_summary()'s
    # contract. Separate columns rather than a blob inside ai_notes because
    # the UI renders them as distinct affordances (a bullet list, a next-steps
    # list, a sentiment chip), and re-parsing them out of prose on every
    # render is how a summary panel starts lying.
    key_points: Mapped[list | None] = mapped_column(JSON, nullable=True)
    next_steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)

    booking: Mapped["CalendarBooking | None"] = relationship()
    lead: Mapped["Lead | None"] = relationship()
    participants: Mapped[list["MeetingParticipant"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class MeetingParticipant(Base):
    """Who was on the call. No updated_at — join/leave times are facts, and a
    row is written once per person per meeting."""

    __tablename__ = "meeting_participants"

    id: Mapped[uuid.UUID] = _uuid_pk()
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    role: Mapped[MeetingParticipantRole] = mapped_column(
        _enum(MeetingParticipantRole), default=MeetingParticipantRole.CLIENT
    )
    joined_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    meeting: Mapped["Meeting"] = relationship(back_populates="participants")
