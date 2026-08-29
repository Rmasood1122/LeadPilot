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
