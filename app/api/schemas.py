"""Pydantic schemas for the intake flow API (Milestone 1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import BatchStage, FlowType, LeadStatus, ProductType, StrategyStatus
from app.services.local_business import BusinessTypeKey, ServiceArea

# --- Products ---------------------------------------------------------


class ProductCreate(BaseModel):
    # Optional: kept for the M6 CLI/SDK's non-interactive flow, which may
    # not have a JWT session. When authenticated (the normal web/app path),
    # the owner is always the JWT holder — this field is ignored there, so
    # it can never be used to create a product under someone else's account.
    user_email: EmailStr | None = Field(default=None, description="Legacy/CLI only — ignored for authenticated requests")
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1)
    type: ProductType
    business_type: BusinessTypeKey | None = Field(
        default=None,
        description="Local business mode: restaurant | healthcare | retail | "
                    "local_service | other. Omit for a non-local business.")


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    type: ProductType
    created_at: datetime
    business_type: str | None = None


# --- Past clients (Flow 1 intake) ------------------------------------


class PastClientIn(BaseModel):
    details: str = Field(min_length=1, description="Who the client was")
    acquisition_story: str = Field(min_length=1, description="How they were acquired")


class PastClientsCreate(BaseModel):
    clients: list[PastClientIn] = Field(min_length=1, max_length=50)


class PastClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    details: str
    acquisition_story: str
    extracted_patterns_json: dict | None


# --- Strategies --------------------------------------------------------


class AutopilotOptIn(BaseModel):
    """Autopilot launch opt-in (docs/features/autopilot-launch.md). Turning it
    on needs `lawful_basis_confirmed: true` and the CURRENT text version
    (GET /strategies/{id}/autopilot or GET /autopilot/lawful-basis) -- 422
    otherwise, and nothing is stored."""
    enabled: bool = False
    lawful_basis_confirmed: bool = False
    lawful_basis_text_version: str | None = Field(default=None, max_length=60)


class StrategyCreate(BaseModel):
    flow_type: FlowType | None = Field(
        default=None,
        description=(
            "Omit to infer: with_clients if the product has past clients, "
            "else no_clients. Explicit with_clients on a product with zero "
            "past clients is rejected."
        ),
    )
    max_budget_usd: float | None = Field(
        default=None, gt=0,
        description=(
            "F-AI-01: the most this strategy's pipeline + verification may spend "
            "on model calls, in US dollars (e.g. 3 or 5). Omit for the server "
            "default. Bounded by the server's minimum ($0.50) and ceiling."
        ),
    )
    autopilot: AutopilotOptIn | None = Field(
        default=None,
        description=("Autopilot launch: when research finishes and verification passes, "
                     "find leads, write the sequence and start outreach automatically. "
                     "Off unless enabled with the lawful-basis confirmation."),
    )
    # Local business mode (docs/features/local-business-mode.md). Only for a
    # product with a business_type; 422 otherwise.
    service_area: ServiceArea | None = Field(
        default=None, description="Local business mode: where the business's "
        "B2B buyers are (city or postal code, country, radius)")
    local_offer: str | None = Field(
        default=None, max_length=500,
        description="Local business mode: what the business offers business buyers")


class StrategyResumeIn(BaseModel):
    max_budget_usd: float | None = Field(
        default=None, gt=0,
        description="New total budget in USD. Must exceed what is already spent.",
    )


class StrategyReverifyIn(BaseModel):
    max_budget_usd: float | None = Field(
        default=None, gt=0,
        description="New total budget in USD. Must exceed what is already spent.",
    )
    max_attempts: int | None = Field(
        default=None, ge=1, le=5,
        description="Judge/fix attempts per verification pass. Omit for the server "
                    "default (not the reduced-plan cap of 2).",
    )


class StrategyPassOverrideIn(BaseModel):
    pass_nos: list[int] = Field(
        min_length=1, max_length=3,
        description="Exactly the failed passes being signed off.",
    )
    reason: str = Field(min_length=1, max_length=2000,
                        description="Why the failure is acceptable (min 20 chars).")
    acknowledge: bool = Field(
        description="Must be true: confirms a human, not the judge, is passing these.")


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    flow_type: FlowType
    status: StrategyStatus
    created_at: datetime
    budget_usd: float | None = None
    spent_usd: float | None = None
    steps_per_phase: int | None = None   # None = the full nine
    planned_steps: int | None = None
    # Local business mode. business_type is the product's (read-only here).
    business_type: str | None = None
    service_area: dict | None = None
    local_offer: str | None = None


class PhaseProgress(BaseModel):
    phase: int
    title: str
    done: int
    total: int


class PipelineProgress(BaseModel):
    pipeline: str  # "strategy" | "gtm"
    done: int
    total: int
    phases: list[PhaseProgress]


class StrategyStatusOut(BaseModel):
    id: uuid.UUID
    flow_type: FlowType
    status: StrategyStatus
    progress: list[PipelineProgress]
    verification: list[dict]
    strategy_document_ready: bool
    gtm_document_ready: bool
    error: str | None
    budget_usd: float | None = None
    spent_usd: float | None = None
    steps_per_phase: int | None = None
    planned_steps: int | None = None


# --- Leads (Milestone 2) ----------------------------------------------


class SourceLeadsRequest(BaseModel):
    max_leads: int | None = Field(default=None, ge=1, le=1000,
        description="Cap for this batch; also capped by LEADS_MAX_PER_RUN")
    icp_criteria: dict | None = Field(default=None,
        description="Explicit criteria (titles, industries, locations, "
                    "company_size_ranges, keywords). Omit to extract them "
                    "from the strategy's ICP research automatically.")


class LeadBatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    strategy_id: uuid.UUID
    stage: BatchStage
    requested_leads: int
    icp_criteria_json: dict | None
    summary_json: dict | None
    created_at: datetime


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: LeadStatus
    source: str
    full_name: str | None
    title: str | None
    company: str | None
    email: str | None
    phone: str | None
    created_at: datetime
    # Feature Group 1. Defaults so a response built from an older row (or a
    # client of the published SDK) is unaffected.
    ai_booking_likelihood: int | None = None
    ai_score_reason: str | None = None
    # Part 1 Feature 2. The four sub-scores travel with every list row so the
    # list can show WHY a prospect ranks where it does, not just that it does.
    # Defaults keep an older row (and the published SDK) unaffected.
    fpta_overall: int | None = None
    fpta_fit: int | None = None
    fpta_problem: int | None = None
    fpta_timing: int | None = None
    fpta_access: int | None = None
    fpta_scored_at: datetime | None = None


class LeadDetailOut(LeadOut):
    strategy_id: uuid.UUID
    batch_id: uuid.UUID | None
    external_id: str | None
    enrichment_json: dict | None
    ai_score_factors: dict | None = None
    ai_scored_at: datetime | None = None
    linkedin_url: str | None = None      # Feature Group 2/5
    # Feature Group 6
    phone_consent_at: datetime | None = None
    phone_consent_source: str | None = None
    last_call_at: datetime | None = None
    last_call_outcome: str | None = None
    # Part 1 Feature 2: the reasons and the evidence behind each sub-score.
    fpta_reasons_json: dict | None = None
    fpta_method: str | None = None


class LeadListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[LeadOut]
