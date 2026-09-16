import { api } from "./client";
import type { FptaDetail } from "../fpta";

/** Part 1 Features 2 + 12 — F-P-T-A scoring and the explainability panel. */

export const getLeadFpta = (leadId: string) =>
  api<FptaDetail>(`/leads/${leadId}/fpta`);

export const rescoreLeadFpta = (leadId: string) =>
  api<FptaDetail>(`/leads/${leadId}/fpta/rescore`, { method: "POST" });

export const rescoreStrategyFpta = (strategyId: string, onlyUnscored = true) =>
  api<{ strategy_id: string; scored: number; only_unscored: boolean }>(
    `/strategies/${strategyId}/leads/fpta/rescore?only_unscored=${onlyUnscored}`,
    { method: "POST" });
