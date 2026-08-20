import { apiClient } from "./client";

export interface PlanDefinition {
  max_strategies: number;
  max_leads_per_strategy: number;
  max_sequence_steps: number;
  channels: string[];
  ab_testing: boolean;
  playbook_access: boolean;
  multi_variate: boolean;
  api_rate_limit_multiplier: number;
  analytics_history_days: number;
  display_name: string;
  upgrade_to: string | null;
}

export interface PlansResponse {
  plans: Record<string, PlanDefinition>;
}

export const plansApi = {
  getAll: (): Promise<PlansResponse> =>
    apiClient.get("/plans").then((r: any) => r.data),
};
