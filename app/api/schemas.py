"""Pydantic schemas for the intake flow API (Milestone 1)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models import BatchStage, FlowType, LeadStatus, ProductType, StrategyStatus

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


class ProductOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str
    type: ProductType
    created_at: datetime


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


class StrategyCreate(BaseModel):
    flow_type: FlowType | None = Field(
        default=None,
        description=(
            "Omit to infer: with_clients if the product has past clients, "
            "else no_clients. Explicit with_clients on a product with zero "
            "past clients is rejected."
        ),
    )


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    flow_type: FlowType
    status: StrategyStatus
    created_at: datetime


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


class LeadListOut(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[LeadOut]
