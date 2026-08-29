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
from datetime import datetime

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
    UniqueConstraint,
    Uuid,
    func,
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
