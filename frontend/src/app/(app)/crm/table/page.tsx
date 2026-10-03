"use client";

/** CRM view 2: the data grid.
 *
 * Wires the pure state in src/lib/crm/grid-state.ts to the server query, the
 * optimistic inline-edit mutation, saved views, bulk actions and CSV export.
 * All the interesting logic lives in the reducer (which the Vitest suite
 * covers) and in the grid component; this page is the composition.
 */

import { useCallback, useMemo, useReducer, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { me } from "@/lib/api/auth";
import {
  useCrmBulkPatch,
  useCrmGrid,
  useCrmPatchLead,
  useCrmRoundRobin,
  useCrmTags,
  useCrmViews,
  useDeleteView,
  useSaveView,
} from "@/lib/api/crm-hooks";
import { getCurrentWorkspace, listMembers } from "@/lib/api/workspaces";
import { bulkOwnerChoices, canDistribute, type TeamContext } from "@/lib/crm/assignment";
import { StrategyScope } from "@/components/crm/CrmChrome";
import { DataGrid } from "@/components/crm/grid/DataGrid";
import { BulkActionBar, GridToolbar } from "@/components/crm/grid/GridToolbar";
import { LeadNotesPanel } from "@/components/crm/grid/LeadNotesPanel";
import {
  gridReducer,
  initialGridState,
  rowsToCsv,
  toSavedViewInput,
  visibleColumns,
} from "@/lib/crm/grid-state";
import { AsyncState } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import type { CrmGridRow, LeadStatus } from "@/lib/api/types";

export default function CrmTablePage() {
  const [state, dispatch] = useReducer(gridReducer, undefined, () =>
    initialGridState(100),
  );
  const [strategyId, setStrategyId] = useState("");
  const [notesLeadId, setNotesLeadId] = useState<string | null>(null);
  const toast = useToast();

  const { data, isLoading, isFetching, error } = useCrmGrid({
    strategyId: strategyId || null,
    filters: state.filters,
    sort: state.sort,
    search: state.search,
    tagIds: state.tagIds,
    limit: state.limit,
    offset: state.offset,
  });

  const { data: viewsData } = useCrmViews("grid");
  const { data: tagsData } = useCrmTags();
  const patchLead = useCrmPatchLead();
  const bulkPatch = useCrmBulkPatch();
  const roundRobin = useCrmRoundRobin();
  const saveView = useSaveView("grid");
  const deleteView = useDeleteView("grid");

  // Team context for assignment. Members and role follow the selected
  // workspace (the X-Workspace-Id header); `me` is the person signed in.
  const { data: membersData } = useQuery({ queryKey: ["members"], queryFn: listMembers });
  const { data: workspaceData } = useQuery({
    queryKey: ["workspace-current"],
    queryFn: getCurrentWorkspace,
  });
  const { data: meData } = useQuery({ queryKey: ["me"], queryFn: me, staleTime: 5 * 60_000 });
  const team = useMemo<TeamContext>(
    () => ({
      members: membersData ?? [],
      meId: meData?.id ?? null,
      role: workspaceData?.role,
    }),
    [membersData, meData, workspaceData],
  );

  const rows = useMemo(() => data?.items ?? [], [data]);
  const views = viewsData?.items ?? [];
  const tags = tagsData?.items ?? [];

  const onEdit = useCallback(
    (leadId: string, patch: Record<string, unknown>) => {
      patchLead.mutate(
        { leadId, patch },
        {
          // The optimistic write already happened in the hook's onMutate and
          // its rollback is handled there. What is left here is telling the
          // user WHY it snapped back — a value that silently reverts with no
          // explanation reads as data loss.
          onError: (mutationError) =>
            toast(
              (mutationError as Error).message ?? "That change was rejected",
              "error",
            ),
        },
      );
    },
    [patchLead, toast],
  );

  const selectedIds = useMemo(() => Array.from(state.selected), [state.selected]);

  const runBulk = useCallback(
    (body: {
      status?: LeadStatus;
      add_tag_ids?: string[];
      remove_tag_ids?: string[];
      owner_user_id?: string | null;
    }) => {
      bulkPatch.mutate(
        { lead_ids: selectedIds, ...body },
        {
          onSuccess: (result) => {
            // Partial success is the documented contract of the endpoint, so
            // the UI has to report it rather than claim everything worked.
            if (result.skipped_count > 0) {
              toast(
                `${result.updated_count} updated, ${result.skipped_count} skipped — ` +
                  `${result.skipped[0]?.reason ?? "not a legal move for those rows"}`,
                "error",
              );
            } else {
              toast(`${result.updated_count} lead(s) updated`, "success");
            }
            dispatch({ type: "clearSelection" });
          },
          onError: (mutationError) =>
            toast((mutationError as Error).message ?? "Bulk update failed", "error"),
        },
      );
    },
    [bulkPatch, selectedIds, toast],
  );

  const runRoundRobin = useCallback(() => {
    roundRobin.mutate(
      { lead_ids: selectedIds },
      {
        onSuccess: (result) => {
          // Already-assigned rows are skipped by design (the endpoint only
          // distributes unassigned leads), so report them rather than hide them.
          toast(
            result.skipped_count > 0
              ? `${result.assigned_count} distributed, ${result.skipped_count} already had an owner`
              : `${result.assigned_count} lead(s) distributed`,
            "success",
          );
          dispatch({ type: "clearSelection" });
        },
        onError: (mutationError) =>
          toast((mutationError as Error).message ?? "Could not distribute leads", "error"),
      },
    );
  }, [roundRobin, selectedIds, toast]);

  /** CSV download. ONE WAY — there is no import counterpart, by design. */
  const exportCsv = useCallback(
    (onlySelected: boolean) => {
      const source: CrmGridRow[] = onlySelected
        ? rows.filter((row) => state.selected.has(row.id))
        : rows;
      if (source.length === 0) {
        toast("Nothing to export", "error");
        return;
      }
      const csv = rowsToCsv(source, visibleColumns(state));
      // A Blob + object URL rather than a data: URI: data: URIs are capped at
      // a couple of MB in some browsers and blocked outright as top-level
      // navigations in others, which a 200-row export can reach.
      const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `leads-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(anchor);
      anchor.click();
      document.body.removeChild(anchor);
      URL.revokeObjectURL(url);
      toast(`Exported ${source.length} row(s)`, "success");
    },
    [rows, state, toast],
  );

  const onSaveView = useCallback(
    (name: string, asNew: boolean) => {
      saveView.mutate(
        {
          viewId: asNew ? undefined : state.viewId ?? undefined,
          body: toSavedViewInput(state, name, false),
        },
        {
          onSuccess: (view) => {
            dispatch({ type: "viewSaved", view });
            toast(`Saved view "${view.name}"`, "success");
          },
          onError: (mutationError) =>
            toast((mutationError as Error).message ?? "Could not save view", "error"),
        },
      );
    },
    [saveView, state, toast],
  );

  const onDeleteView = useCallback(
    (viewId: string) => {
      deleteView.mutate(viewId, {
        onSuccess: () => {
          if (state.viewId === viewId) dispatch({ type: "resetView" });
          toast("View deleted", "success");
        },
      });
    },
    [deleteView, state.viewId, toast],
  );

  const total = data?.total ?? 0;
  const page = Math.floor(state.offset / state.limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / state.limit));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">Leads</h2>
          <p className="text-xs text-muted-foreground">
            Edit in place. Changes save as you go and appear for anyone else
            watching. CSV leaves as a download only — this grid is the editing
            surface.
          </p>
        </div>
        <StrategyScope value={strategyId} onChange={setStrategyId} />
      </div>

      <GridToolbar
        state={state}
        dispatch={dispatch}
        views={views}
        tags={tags}
        onSaveView={onSaveView}
        onDeleteView={onDeleteView}
        onExport={() => exportCsv(false)}
        totalRows={total}
        isSaving={saveView.isPending}
      />

      <AsyncState
        isLoading={isLoading}
        error={error}
        empty={!isLoading && rows.length === 0}
        emptyLabel={
          state.search || Object.keys(state.filters).length > 0
            ? "No leads match these filters."
            : "No leads yet. Source leads from a campaign to fill this table."
        }
      >
        <DataGrid
          rows={rows}
          state={state}
          dispatch={dispatch}
          pageOffset={state.offset}
          totalRows={total}
          onEdit={onEdit}
          onOpenNotes={setNotesLeadId}
          isFetching={isFetching}
          team={team}
        />

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            Page {page} of {pageCount}
          </span>
          <span className="flex gap-2">
            <Button
              size="sm"
              variant="outline"
              disabled={state.offset === 0}
              onClick={() =>
                dispatch({ type: "setOffset", offset: state.offset - state.limit })
              }
            >
              Previous
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!data?.has_more}
              onClick={() =>
                dispatch({ type: "setOffset", offset: state.offset + state.limit })
              }
            >
              Next
            </Button>
          </span>
        </div>
      </AsyncState>

      <BulkActionBar
        count={selectedIds.length}
        tags={tags}
        busy={bulkPatch.isPending || roundRobin.isPending}
        onStatus={(status) => runBulk({ status })}
        onAddTag={(tagId) => runBulk({ add_tag_ids: [tagId] })}
        onRemoveTag={(tagId) => runBulk({ remove_tag_ids: [tagId] })}
        assignees={bulkOwnerChoices(team)}
        onAssign={(ownerId) => runBulk({ owner_user_id: ownerId })}
        onRoundRobin={canDistribute(team.role) ? runRoundRobin : undefined}
        onExport={() => exportCsv(true)}
        onClear={() => dispatch({ type: "clearSelection" })}
      />

      {notesLeadId && (
        <LeadNotesPanel
          leadId={notesLeadId}
          onClose={() => setNotesLeadId(null)}
        />
      )}
    </div>
  );
}
