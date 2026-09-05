"use client";

/** M9 React Query hooks. Same pattern as src/lib/api/hooks.ts — components
 *  never call the domain module directly.
 *
 * ON refetchInterval
 * Every hook here keeps a slow poll. It is NOT the primary update path any
 * more — the SSE subscription in CrmRealtimeContext invalidates these keys
 * the moment something changes, which is what actually keeps the screen
 * live. The timer is the safety net for the cases the stream cannot cover:
 * Redis down, the kill switch on, a proxy that ate the connection, a phone
 * that came back from the background before the reconnect landed.
 *
 * So the interval is deliberately long (60s, not the 4-15s the polling-only
 * screens in hooks.ts use). At 60s the fallback is invisible when the stream
 * works and tolerable when it does not.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as crm from "./crm";
import type {
  CrmActivityKind,
  CrmFilter,
  CrmGridPage,
  CrmSort,
  LeadStatus,
} from "./types";

/** Fallback poll interval. See the module note: the SSE stream is primary. */
const FALLBACK_POLL_MS = 60_000;

// --------------------------------------------------------------------------
// Dashboards
// --------------------------------------------------------------------------

export function useCrmPipeline(strategyId?: string | null) {
  return useQuery({
    queryKey: ["crm-pipeline", strategyId ?? "all"],
    queryFn: () => crm.getPipelineDashboard(strategyId),
    refetchInterval: FALLBACK_POLL_MS,
  });
}

export function useCrmLeadsAnalytics(
  strategyId?: string | null,
  stuckAfterDays = 7,
) {
  return useQuery({
    queryKey: ["crm-leads", strategyId ?? "all", stuckAfterDays],
    queryFn: () => crm.getLeadsDashboard(strategyId, stuckAfterDays),
    refetchInterval: FALLBACK_POLL_MS,
  });
}

export function useCrmCampaigns(strategyId?: string | null) {
  return useQuery({
    queryKey: ["crm-campaigns", strategyId ?? "all"],
    queryFn: () => crm.getCampaignsDashboard(strategyId),
    refetchInterval: FALLBACK_POLL_MS,
  });
}

export function useCrmActivity(params: {
  strategyId?: string | null;
  leadId?: string | null;
  kinds?: CrmActivityKind[];
  limit?: number;
} = {}) {
  return useQuery({
    queryKey: [
      "crm-activity",
      params.strategyId ?? "all",
      params.leadId ?? "all",
      (params.kinds ?? []).join(","),
    ],
    queryFn: () => crm.getActivityFeed(params),
    refetchInterval: FALLBACK_POLL_MS,
  });
}

// --------------------------------------------------------------------------
// Grid
// --------------------------------------------------------------------------

export interface GridParams {
  strategyId?: string | null;
  filters: Record<string, CrmFilter>;
  sort: CrmSort[];
  search: string;
  tagIds: string[];
  limit: number;
  offset: number;
}

export function useCrmGrid(params: GridParams) {
  return useQuery({
    queryKey: [
      "crm-grid",
      params.strategyId ?? "all",
      params.filters,
      params.sort,
      params.search,
      params.tagIds,
      params.limit,
      params.offset,
    ],
    queryFn: () =>
      crm.queryGrid({
        strategy_id: params.strategyId,
        filters: params.filters,
        sort: params.sort,
        search: params.search || null,
        tag_ids: params.tagIds,
        limit: params.limit,
        offset: params.offset,
      }),
    // Keeps the previous page on screen while the next one loads, so paging
    // and re-sorting do not blank the grid to a skeleton every time.
    placeholderData: (previous) => previous,
    refetchInterval: FALLBACK_POLL_MS,
  });
}

/** Inline cell edit, applied optimistically and rolled back on failure.
 *
 * A grid that waits for a round trip before showing the new value feels
 * broken — the user has already tabbed to the next cell. So the cache is
 * updated first, and if the request fails the snapshot is restored and the
 * caller shows a toast. This is the mutation the brief calls for explicitly.
 */
export function useCrmPatchLead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ leadId, patch }: { leadId: string; patch: crm.LeadPatch }) =>
      crm.patchLead(leadId, patch),

    onMutate: async ({ leadId, patch }) => {
      // Stop in-flight refetches from landing on top of the optimistic write.
      await queryClient.cancelQueries({ queryKey: ["crm-grid"] });
      const snapshot = queryClient.getQueriesData<CrmGridPage>({
        queryKey: ["crm-grid"],
      });

      queryClient.setQueriesData<CrmGridPage>({ queryKey: ["crm-grid"] }, (page) => {
        if (!page) return page;
        return {
          ...page,
          items: page.items.map((row) =>
            row.id === leadId
              ? {
                  ...row,
                  ...(patch.status !== undefined ? { status: patch.status } : {}),
                  ...(patch.owner_user_id !== undefined
                    ? { owner_user_id: patch.owner_user_id }
                    : {}),
                  ...(patch.priority !== undefined
                    ? { priority: patch.priority }
                    : {}),
                  ...(patch.next_action_at !== undefined
                    ? { next_action_at: patch.next_action_at }
                    : {}),
                  ...(patch.custom
                    ? { custom: { ...row.custom, ...patch.custom } }
                    : {}),
                }
              : row,
          ),
        };
      });

      return { snapshot };
    },

    onError: (_error, _vars, context) => {
      // Restore EVERY key we touched, not just the active one: the user may
      // have paged or re-sorted between the optimistic write and the failure,
      // and leaving a stale optimistic value in an inactive cache entry means
      // it reappears the moment they page back.
      for (const [key, data] of context?.snapshot ?? []) {
        queryClient.setQueryData(key, data);
      }
    },

    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["crm-grid"] });
      void queryClient.invalidateQueries({ queryKey: ["crm-activity"] });
    },
  });
}

export function useCrmBulkPatch() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      lead_ids: string[];
      status?: LeadStatus;
      add_tag_ids?: string[];
      remove_tag_ids?: string[];
    }) => crm.bulkPatchLeads(body),
    // NOT optimistic. A bulk status change is partially applied by design —
    // rows whose current status makes the move illegal are skipped — so the
    // client cannot know the result without asking. Showing 200 rows as moved
    // and then silently reverting 40 is worse than a half-second wait.
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["crm-grid"] });
      void queryClient.invalidateQueries({ queryKey: ["crm-pipeline"] });
      void queryClient.invalidateQueries({ queryKey: ["crm-activity"] });
    },
  });
}

// --------------------------------------------------------------------------
// Notes / tags / fields / views
// --------------------------------------------------------------------------

export function useCrmNotes(leadId: string | null) {
  return useQuery({
    queryKey: ["crm-notes", leadId],
    queryFn: () => crm.listNotes(leadId as string),
    enabled: !!leadId,
  });
}

export function useCreateNote(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => crm.createNote(leadId, body),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["crm-notes", leadId] });
      void queryClient.invalidateQueries({ queryKey: ["crm-grid"] });
    },
  });
}

export function useDeleteNote(leadId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (noteId: string) => crm.deleteNote(noteId),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["crm-notes", leadId] });
      void queryClient.invalidateQueries({ queryKey: ["crm-grid"] });
    },
  });
}

export function useCrmTags() {
  return useQuery({ queryKey: ["crm-tags"], queryFn: crm.listTags });
}

export function useCreateTag() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ name, colorToken }: { name: string; colorToken?: string }) =>
      crm.createTag(name, colorToken),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["crm-tags"] }),
  });
}

export function useCrmFields() {
  return useQuery({ queryKey: ["crm-fields"], queryFn: crm.listFields });
}

export function useCrmViews(viewType: "grid" | "dashboard" = "grid") {
  return useQuery({
    queryKey: ["crm-views", viewType],
    queryFn: () => crm.listViews(viewType),
  });
}

export function useSaveView(viewType: "grid" | "dashboard" = "grid") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      viewId,
      body,
    }: {
      viewId?: string;
      body: crm.SavedViewInput;
    }) => (viewId ? crm.updateView(viewId, body) : crm.createView(body)),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["crm-views", viewType] }),
  });
}

export function useDeleteView(viewType: "grid" | "dashboard" = "grid") {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (viewId: string) => crm.deleteView(viewId),
    onSettled: () =>
      queryClient.invalidateQueries({ queryKey: ["crm-views", viewType] }),
  });
}
