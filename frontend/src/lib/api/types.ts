/** Typed mirrors of the backend Pydantic/response shapes the UI consumes. */

export interface UserOut {
  id: string;
  email: string;
  plan: string;
  is_admin?: boolean;
  /** Feature 1. Until this is true every authenticated endpoint answers 403
   *  EMAIL_NOT_VERIFIED, so the UI routes the user to /check-email instead of
   *  the dashboard. Optional because a cached response from a backend that
   *  predates the feature will not carry it. */
  email_verified?: boolean;
}

export interface TokenBundle {
  user: UserOut;
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  /** Present on the /auth/signup response only. */
  email_verification_required?: boolean;
  /** False when the account was created but the mail transport was down —
   *  the check-email screen says so rather than telling the user to look for
   *  a message that was never sent. */
  verification_email_sent?: boolean;
}

// --------------------------------------------------------------------------
// Learn LeadPilot — tutorials (Feature 2)
// --------------------------------------------------------------------------

export type TutorialLevel = "beginner" | "intermediate" | "advanced";

export interface TutorialProgress {
  position_seconds: number;
  duration_seconds: number | null;
  /** Furthest point reached, 0-100. Monotonic: scrubbing back never lowers it. */
  percent: number;
  completed: boolean;
  completed_at: string | null;
  last_watched_at: string | null;
  /** false when the user has no progress row at all — "not started". */
  started: boolean;
}

export interface Tutorial {
  slug: string;
  title: string;
  description: string;
  level: TutorialLevel;
  order: number;
  /** null until a real video exists. See is_placeholder. */
  youtube_id: string | null;
  duration_seconds: number | null;
  /** true => show a "coming soon" panel, NOT an iframe pointing at nothing. */
  is_placeholder: boolean;
  progress: TutorialProgress;
}

/** A catalogue row as the ADMIN sees it — includes unpublished drafts. */
export interface AdminTutorial {
  id: string;
  slug: string;
  title: string;
  description: string;
  level: TutorialLevel;
  order: number;
  youtube_id: string | null;
  duration_seconds: number | null;
  is_placeholder: boolean;
  is_published: boolean;
}

export interface AdminTutorialList {
  tutorials: AdminTutorial[];
  levels: { level: TutorialLevel; label: string }[];
  published_count: number;
  total_count: number;
}

/** PUT payload. `slug` is absent on purpose — renaming one orphans every
 *  progress row that points at it, so the API cannot do it at all. */
export interface AdminTutorialPatch {
  title?: string;
  description?: string;
  level?: TutorialLevel;
  youtube_id?: string | null;
  duration_seconds?: number | null;
  sort_order?: number;
  is_published?: boolean;
}

export interface TutorialLevelSummary {
  label: string;
  total: number;
  completed: number;
}

export interface TutorialSummary {
  total: number;
  completed: number;
  percent: number;
  by_level: Record<TutorialLevel, TutorialLevelSummary>;
}

export interface TutorialBadge {
  slug: string;
  label: string;
  description: string;
  level: TutorialLevel | null;
  earned: boolean;
  earned_at: string | null;
  required_total: number;
  required_completed: number;
}

export interface TutorialCatalogue {
  tutorials: Tutorial[];
  levels: { level: TutorialLevel; label: string }[];
  /** Always describes the WHOLE catalogue — never the filtered result set. */
  summary: TutorialSummary;
  badges: TutorialBadge[];
  query: { q: string | null; level: string | null };
}

// --------------------------------------------------------------------------
// AI support chat (Feature 3)
// --------------------------------------------------------------------------

export interface FaqEntry {
  id: string;
  question: string;
  answer: string;
}

export interface SupportFaq {
  faq: FaqEntry[];
  /** false => the kill switch is on; the widget offers tickets only. */
  chat_enabled: boolean;
}

/** Why the user got this text. Mirrors app/services/support_chat.py. */
export type AnswerReason =
  | "answered"
  | "off_topic"
  | "low_confidence"
  | "model_error"
  | "malformed_response"
  | "empty_answer"
  | "empty_question";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  reason: AnswerReason | null;
  confidence: number | null;
  faq_ids: string[];
  suggest_ticket: boolean;
  created_at: string | null;
}

export interface ChatAnswer {
  text: string;
  on_topic: boolean;
  confidence: number;
  faq_ids: string[];
  suggest_ticket: boolean;
  reason: AnswerReason;
}

export interface ChatReply {
  session_id: string;
  answer: ChatAnswer;
  message: ChatMessage;
}

export interface ChatSession {
  id: string;
  title: string | null;
  created_at: string | null;
  last_message_at: string | null;
  messages?: ChatMessage[];
}

export interface SupportTicket {
  id: string;
  subject: string;
  body: string;
  status: "open" | "resolved";
  chat_session_id: string | null;
  created_at: string | null;
  resolved_at: string | null;
  resolution_note: string | null;
}

export interface AdminSupportTicket extends SupportTicket {
  user_id: string;
  user_email: string | null;
}

export interface AdminTutorialCompletion {
  slug: string;
  title: string;
  level: string;
  is_published: boolean;
  started_count: number;
  completed_count: number;
  in_progress_count: number;
}

export interface AdminTutorialCompletions {
  active_learners: number;
  total_completions: number;
  tutorials: AdminTutorialCompletion[];
}

export type FlowType = "with_clients" | "no_clients";

export interface StrategyOut {
  id: string;
  product_id: string;
  flow_type: FlowType;
  status:
    | "pending"
    | "researching"
    | "verifying"
    | "verified"
    | "needs_human_review"
    | "executing"
    | "failed";
  progress: PhaseProgress[];
  verification: VerificationPass[];
  strategy_document_ready: boolean;
  gtm_document_ready: boolean;
  error: string | null;
}

export interface PhaseProgress {
  pipeline: "strategy" | "gtm";
  phase: number;
  done: number;
  total: number;
  steps?: StepOut[];
}

export interface StepOut {
  step_no: number;
  step_id: string;
  name: string;
  output: string;
}

export interface VerificationPass {
  pass_no: number;
  name: string;
  result: "PASS" | "FAIL";
  attempts: number;
  fix?: string | null;
}

export type LeadStatus =
  | "sourced"
  | "enriched"
  | "email_found"
  | "verified"
  | "flagged"
  | "dropped"
  | "contacted"
  | "replied"
  | "meeting_booked";

export interface LeadOut {
  id: string;
  full_name: string | null;
  title: string | null;
  company: string | null;
  email: string | null;
  phone: string | null;
  status: LeadStatus;
  enrichment_json: Record<string, unknown> | null;
  whatsapp_opted_in?: boolean;
}

export interface ChannelStats {
  sent_total: number;
  delivery_rate: number | null;
  reply_rate: number | null;
  sends_today: number | null;
  daily_cap_today: number | null;
  window_open_count?: number;
  needs_template_count?: number;
  templates_in_use?: TemplateOut[];
}

export interface CampaignOverview {
  strategy_id: string;
  campaign_state: string;
  campaign_pause_reason: string | null;
  leads_by_status: Record<LeadStatus, number>;
  sent_total: number;
  reply_rate: number;
  bounce_rate: number;
  meetings_booked?: number;
  channels: { email: ChannelStats; whatsapp: ChannelStats };
}

export interface TemplateOut {
  id: string;
  name: string;
  language: string;
  version?: number;
  category?: string;
  status: "draft" | "submitted" | "approved" | "rejected";
  body?: string | null;
  variable_descriptions?: Record<string, string>;
  rejection_reason?: string | null;
}

export interface AnalyticsPoint {
  bucket: string;
  channel: string;
  event: string;
  count: number;
}

export interface AnalyticsOut {
  strategy_id: string;
  granularity: string;
  series: AnalyticsPoint[];
  variants: Record<string, Record<string, number>>;
  learning_insights: unknown | null;
}

export interface SequenceStepOut {
  step_no: number;
  template: string;
  variant: string;
  delay_days: number;
  channel?: "email" | "whatsapp" | null;
  whatsapp_kind?: "template" | "text" | null;
  whatsapp_template_id?: string | null;
}

export interface SequenceOut {
  id: string;
  strategy_id: string;
  name: string;
  channel: "email" | "whatsapp";
  status: string;
  booking_url: string | null;
  steps: SequenceStepOut[];
}

// --------------------------------------------------------------------------
// Native CRM (M9)
// --------------------------------------------------------------------------

export interface CrmFunnelStage {
  stage: LeadStatus;
  /** Leads sitting AT this stage right now. */
  current: number;
  /** Leads at this stage OR any later one — what a funnel bar shows. */
  reached: number;
  /** reached / the previous stage's reached. null for the first stage. */
  conversion_from_previous: number | null;
}

export interface CrmPipelineDashboard {
  strategy_id: string | null;
  total_leads: number;
  /** Excludes dropped and meeting_booked — those are finished, not active. */
  active_leads: number;
  by_status: Record<LeadStatus, number>;
  funnel: CrmFunnelStage[];
  meetings_booked_week: number;
  meetings_booked_month: number;
  bookings_trend: { bucket: string; count: number }[];
  top_strategy: {
    strategy_id: string;
    product_name: string;
    meetings_booked: number;
  } | null;
}

export interface CrmVelocityRow {
  stage: LeadStatus;
  leads: number;
  /** Leads with a real stage_entered_at measurement. */
  measured: number;
  /** Leads whose figure is derived from updated_at instead. */
  estimated: number;
  avg_days_in_stage: number;
  /** True only when every lead in the stage has a real measurement. */
  fully_measured: boolean;
}

export interface CrmLeadsDashboard {
  strategy_id: string | null;
  velocity: CrmVelocityRow[];
  sources: { source: string; count: number }[];
  verification: {
    verified: number;
    flagged: number;
    dropped: number;
    total: number;
    /** null (not 0) when nothing was verified — "no data", not "all failed". */
    verified_ratio: number | null;
  };
  stuck_after_days: number;
  stuck_leads: {
    lead_id: string;
    status: LeadStatus;
    days_in_stage: number;
    measured: boolean;
  }[];
  stuck_count: number;
}

export interface CrmSequencePerformance {
  sequence_id: string;
  strategy_id: string;
  name: string;
  channel: string;
  status: string;
  sent: number;
  replied: number;
  booked: number;
  reply_rate: number | null;
  booking_rate: number | null;
}

export interface CrmChannelPerformance {
  channel: string;
  sent: number;
  replied: number;
  booked: number;
  bounced: number;
  reply_rate: number | null;
  booking_rate: number | null;
  bounce_rate: number | null;
}

export interface CrmVariantPerformance {
  variant: string;
  sent: number;
  replied: number;
  booked: number;
  reply_rate: number | null;
  booking_rate: number | null;
}

export interface CrmCampaignsDashboard {
  strategy_id: string | null;
  sequences: CrmSequencePerformance[];
  channels: CrmChannelPerformance[];
  variants: CrmVariantPerformance[];
  bounce: {
    sent: number;
    bounced: number;
    rate: number;
    pause_threshold: number;
    over_threshold: boolean;
  };
  paused_campaigns: {
    strategy_id: string;
    campaign_state: string;
    reason: string | null;
    product_name: string;
  }[];
}

export type CrmActivityKind =
  | "lead_created"
  | "status_changed"
  | "note_added"
  | "note_deleted"
  | "tag_added"
  | "tag_removed"
  | "field_changed"
  | "owner_changed"
  | "reply_received"
  | "meeting_booked";

export interface CrmActivityItem {
  id: string;
  lead_id: string;
  strategy_id: string | null;
  kind: CrmActivityKind;
  from_value: string | null;
  to_value: string | null;
  meta: Record<string, unknown> | null;
  ts: string | null;
  /** null means the pipeline did it, not a person. */
  actor_user_id: string | null;
  lead: { full_name: string | null; company: string | null; email: string | null };
}

export interface CrmActivityPage {
  items: CrmActivityItem[];
  has_more: boolean;
  /** Opaque cursor — pass back as `before`. Carries (ts, id), not just a
   *  timestamp, because activity timestamps tie on both dialects. */
  next_before: string | null;
}

export interface CrmTag {
  id: string;
  name: string;
  /** A THEME TOKEN name (primary/accent/success/warning/destructive/muted),
   *  never a hex — the app recolors from CSS variables. */
  color_token: string;
}

export interface CrmNote {
  id: string;
  lead_id: string;
  body: string;
  author_user_id: string | null;
  created_at: string | null;
  updated_at?: string | null;
}

export interface CrmGridRow {
  id: string;
  strategy_id: string;
  full_name: string | null;
  title: string | null;
  company: string | null;
  email: string | null;
  phone: string | null;
  status: LeadStatus;
  source: string;
  created_at: string | null;
  updated_at: string | null;
  tags: CrmTag[];
  custom: Record<string, unknown>;
  note_count: number;
  owner_user_id: string | null;
  priority: string | null;
  next_action_at: string | null;
}

export interface CrmGridPage {
  items: CrmGridRow[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export type CrmFilterOp =
  | "eq"
  | "contains"
  | "in"
  | "not_in"
  | "gte"
  | "lte"
  | "is_empty"
  | "is_not_empty";

export interface CrmFilter {
  op: CrmFilterOp;
  value: unknown;
}

export interface CrmSort {
  key: string;
  dir: "asc" | "desc";
}

export interface CrmColumnState {
  key: string;
  width: number;
  visible: boolean;
}

export interface CrmSavedView {
  id: string;
  name: string;
  view_type: "grid" | "dashboard";
  filters_json: Record<string, CrmFilter>;
  sort_json: CrmSort[];
  columns_json: CrmColumnState[];
  is_default: boolean;
  created_at: string | null;
}

export type CrmFieldType = "text" | "number" | "date" | "bool" | "select";

export interface CrmCustomField {
  id: string;
  key: string;
  label: string;
  field_type: CrmFieldType;
  options_json: string[] | null;
  sort_order: number;
}

/** Event names the SSE stream emits. */
export type CrmStreamEventName =
  | "ready"
  | "reconnect"
  | "lead.updated"
  | "lead.status_changed"
  | "note.created"
  | "outcome.created"
  | "activity.created";
