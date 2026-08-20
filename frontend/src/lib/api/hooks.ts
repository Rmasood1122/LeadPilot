"use client";

/** React Query hooks — the ONLY way components read backend state. */

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import * as strategies from "./strategies";
import * as leads from "./leads";
import * as campaigns from "./campaigns";
import * as integrations from "./integrations";
import type { LeadStatus } from "./types";

export function useStrategy(id: string) {
  return useQuery({
    queryKey: ["strategy", id],
    queryFn: () => strategies.getStrategy(id),
    // live pipeline progress: poll while researching/verifying
    refetchInterval: (query) =>
      query.state.data &&
      ["researching", "verifying", "pending"].includes(query.state.data.status)
        ? 4000
        : false,
  });
}

export function useStrategies() {
  return useQuery({
    queryKey: ["strategies"],
    queryFn: strategies.listStrategies,
  });
}

export function useStrategyDocument(id: string, enabled: boolean) {
  return useQuery({
    queryKey: ["strategy-document", id],
    queryFn: () => strategies.getStrategyDocument(id),
    enabled,
  });
}

export function useAnalytics(id: string, granularity: string) {
  return useQuery({
    queryKey: ["analytics", id, granularity],
    queryFn: () => strategies.getAnalytics(id, granularity),
    enabled: !!id,
  });
}

export function useLeads(strategyId: string) {
  return useQuery({
    queryKey: ["leads", strategyId],
    queryFn: () => leads.listLeads(strategyId),
    enabled: !!strategyId,
  });
}

export function useUpdateLeadStatus(strategyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, status }: { id: string; status: LeadStatus }) =>
      leads.updateLeadStatus(id, status),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["leads", strategyId] }),
  });
}

export function useCampaign(strategyId: string) {
  return useQuery({
    queryKey: ["campaign", strategyId],
    queryFn: () => campaigns.getCampaign(strategyId),
    enabled: !!strategyId,
    refetchInterval: 15000,
  });
}

export function useSequences(strategyId: string) {
  return useQuery({
    queryKey: ["sequences", strategyId],
    queryFn: () => campaigns.listSequences(strategyId),
    enabled: !!strategyId,
  });
}

export function useTemplates() {
  return useQuery({
    queryKey: ["wa-templates"],
    queryFn: campaigns.listTemplates,
  });
}

export function useIntegrations() {
  return useQuery({
    queryKey: ["integrations"],
    queryFn: integrations.getIntegrations,
  });
}

export function useSuppression() {
  return useQuery({
    queryKey: ["suppression"],
    queryFn: integrations.listSuppression,
  });
}
