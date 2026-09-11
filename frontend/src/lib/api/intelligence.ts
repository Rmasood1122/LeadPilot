/** Feature Group 1 — consensus zones, market signals, strategy versions,
 *  lead rescoring. */

import { api } from "./client";
import type { LeadScoreFactors } from "./types";

export interface UncertainZone {
  id: string;
  pipeline: "strategy" | "gtm";
  phase: number;
  step_no: number;
  section_title: string;
  topic: string;
  claude_position: string;
  gpt_position: string;
  severity: "medium" | "high";
  similarity: number | null;
}

export interface MarketSignal {
  type: "funding" | "hiring" | "launch" | "news";
  title: string;
  company: string | null;
  source: "google_news" | "apollo" | string;
  url: string | null;
  published_at: string | null;
  query?: string;
}

export interface MarketSignals {
  queries: string[];
  fetched_at: string;
  signals: MarketSignal[];
  errors: string[];
}

export interface VersionChanges {
  diagnosis: string;
  messaging_angle: { current: string; proposed: string; rationale: string };
  channel: { recommended: string; rationale: string };
  icp_refinement: { changes: string[]; rationale: string };
  revised_messaging: string;
}

export interface StrategyVersionSummary {
  id: string;
  version_no: number;
  parent_version_id: string | null;
  change_summary: string | null;
  changes_json: VersionChanges | null;
  outcome_snapshot_json: Record<string, unknown> | null;
  trigger: "original" | "idle_no_replies" | "manual" | string;
  status: "original" | "proposed" | "applied" | "superseded" | "dismissed" | string;
  applied_at: string | null;
  created_at: string;
}

export interface StrategyVersion extends StrategyVersionSummary {
  document: string;
}

export interface StrategyIntelligence {
  consensus_status: "complete" | "partial" | null;
  zones: UncertainZone[];
  market_signals: MarketSignals | null;
  market_signals_fetched_at: string | null;
  versions: StrategyVersionSummary[];
}

export interface ModelOutput {
  provider: "anthropic" | "openai" | string;
  model: string;
  output: string | null;
  error: string | null;
  latency_ms: number | null;
}

export function getIntelligence(strategyId: string): Promise<StrategyIntelligence> {
  return api(`/strategies/${strategyId}/intelligence`);
}

export function getModelOutputs(
  strategyId: string,
  stepNo: number,
  pipeline: "strategy" | "gtm" = "strategy",
): Promise<ModelOutput[]> {
  return api(`/strategies/${strategyId}/model-outputs?step_no=${stepNo}&pipeline=${pipeline}`);
}

export function refreshMarketSignals(strategyId: string): Promise<{ queued: boolean }> {
  return api(`/strategies/${strategyId}/market-signals/refresh`, { method: "POST" });
}

export function getVersion(strategyId: string, versionId: string): Promise<StrategyVersion> {
  return api(`/strategies/${strategyId}/versions/${versionId}`);
}

export function mutateStrategy(strategyId: string): Promise<StrategyVersion> {
  return api(`/strategies/${strategyId}/mutate`, { method: "POST" });
}

export function applyVersion(strategyId: string, versionId: string): Promise<StrategyVersion> {
  return api(`/strategies/${strategyId}/versions/${versionId}/apply`, { method: "POST" });
}

export function dismissVersion(strategyId: string, versionId: string): Promise<StrategyVersion> {
  return api(`/strategies/${strategyId}/versions/${versionId}/dismiss`, { method: "POST" });
}

export function rescoreStrategyLeads(strategyId: string): Promise<{ queued: boolean }> {
  return api(`/strategies/${strategyId}/leads/rescore`, { method: "POST" });
}

export function rescoreLead(leadId: string): Promise<{
  lead_id: string;
  ai_booking_likelihood: number | null;
  ai_score_reason: string | null;
  ai_score_factors: LeadScoreFactors | null;
  ai_scored_at: string | null;
}> {
  return api(`/leads/${leadId}/rescore`, { method: "POST" });
}
