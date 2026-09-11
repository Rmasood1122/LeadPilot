"use client";

/** Grid toolbar: search, filters, saved views, column visibility, CSV export.
 *
 * The saved-view controls are the reason this is server-backed rather than a
 * localStorage blob: a view is the user's own work, and it has to be there on
 * their phone and after they clear site data.
 */

import { useState } from "react";
import { Columns3, Download, Filter, Plus, Save, X } from "lucide-react";

import type { CrmSavedView, CrmTag, LeadStatus } from "@/lib/api/types";
import {
  type GridAction,
  type GridState,
  GRID_COLUMNS,
  activeFilterCount,
  describeFilter,
} from "@/lib/crm/grid-state";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const STATUSES: LeadStatus[] = [
  "sourced",
  "enriched",
  "email_found",
  "verified",
  "flagged",
  "dropped",
  "contacted",
  "replied",
  "meeting_booked",
  "opportunity",
  "closed_won",
  "closed_lost",
  "disqualified",
];

export function GridToolbar({
  state,
  dispatch,
  views,
  tags,
  onSaveView,
  onDeleteView,
  onExport,
  totalRows,
  isSaving,
}: {
  state: GridState;
  dispatch: (action: GridAction) => void;
  views: CrmSavedView[];
  tags: CrmTag[];
  onSaveView: (name: string, asNew: boolean) => void;
  onDeleteView: (viewId: string) => void;
  onExport: () => void;
  totalRows: number;
  isSaving: boolean;
}) {
  const [showFilters, setShowFilters] = useState(false);
  const [showColumns, setShowColumns] = useState(false);
  const [newViewName, setNewViewName] = useState("");
  const filterCount = activeFilterCount(state);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          type="search"
          value={state.search}
          onChange={(event) =>
            dispatch({ type: "setSearch", value: event.target.value })
          }
          placeholder="Search name, company, email, title"
          aria-label="Search leads"
          className="h-9 min-w-[16rem] flex-1 rounded border border-border bg-card px-3 text-sm"
        />

        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowFilters((open) => !open)}
          aria-expanded={showFilters}
        >
          <Filter size={14} aria-hidden="true" />
          Filters
          {filterCount > 0 && <Badge tone="primary">{filterCount}</Badge>}
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowColumns((open) => !open)}
          aria-expanded={showColumns}
        >
          <Columns3 size={14} aria-hidden="true" />
          Columns
        </Button>

        <Button variant="outline" size="sm" onClick={onExport} title="Download the current page as CSV">
          <Download size={14} aria-hidden="true" />
          Export CSV
        </Button>

        <span className="ml-auto text-xs text-muted-foreground tabular-nums">
          {totalRows.toLocaleString()} lead{totalRows === 1 ? "" : "s"}
        </span>
      </div>

      {/* Saved views */}
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Views:</span>
        {views.length === 0 && (
          <span className="text-xs text-muted-foreground">none saved yet</span>
        )}
        {views.map((view) => (
          <span key={view.id} className="flex items-center">
            <button
              type="button"
              onClick={() => dispatch({ type: "loadView", view })}
              aria-current={state.viewId === view.id ? "true" : undefined}
              className={cn(
                "rounded-l border border-border px-2 py-1 text-xs",
                state.viewId === view.id
                  ? "bg-primary text-primary-foreground"
                  : "bg-card hover:bg-muted",
              )}
            >
              {view.name}
              {view.is_default && <span aria-label=" (default)"> ★</span>}
            </button>
            <button
              type="button"
              onClick={() => onDeleteView(view.id)}
              aria-label={`Delete view ${view.name}`}
              className="rounded-r border border-l-0 border-border bg-card px-1.5 py-1 text-muted-foreground hover:text-[rgb(var(--destructive))]"
            >
              <X size={12} aria-hidden="true" />
            </button>
          </span>
        ))}

        {/* "Unsaved changes" is not decoration: a user who built a filter set
            on top of a saved view and navigates away loses it silently
            otherwise. */}
        {state.viewId && state.dirty && (
          <>
            <Badge tone="warning">unsaved changes</Badge>
            <Button
              size="sm"
              variant="outline"
              disabled={isSaving}
              onClick={() => onSaveView(state.viewName ?? "View", false)}
            >
              <Save size={14} aria-hidden="true" />
              Update
            </Button>
          </>
        )}

        <span className="flex items-center gap-1">
          <input
            value={newViewName}
            onChange={(event) => setNewViewName(event.target.value)}
            placeholder="Save current as…"
            aria-label="Name for a new saved view"
            className="h-7 w-40 rounded border border-border bg-card px-2 text-xs"
          />
          <Button
            size="sm"
            variant="outline"
            disabled={!newViewName.trim() || isSaving}
            onClick={() => {
              onSaveView(newViewName.trim(), true);
              setNewViewName("");
            }}
          >
            <Plus size={14} aria-hidden="true" />
            Save
          </Button>
        </span>

        {(filterCount > 0 || state.viewId) && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => dispatch({ type: "resetView" })}
          >
            Reset
          </Button>
        )}
      </div>

      {showFilters && (
        <div className="space-y-2 rounded border border-border bg-card p-3">
          <div className="flex flex-wrap gap-3">
            <label className="flex items-center gap-2 text-xs">
              Status
              <select
                multiple
                size={4}
                value={
                  (state.filters.status?.value as string[] | undefined) ?? []
                }
                onChange={(event) => {
                  const value = Array.from(
                    event.target.selectedOptions,
                    (option) => option.value,
                  );
                  dispatch({
                    type: "setFilter",
                    key: "status",
                    filter: value.length ? { op: "in", value } : null,
                  });
                }}
                aria-label="Filter by status"
                className="rounded border border-border bg-card px-2 py-1 text-xs"
              >
                {STATUSES.map((status) => (
                  <option key={status} value={status}>
                    {status.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-2 text-xs">
              Company contains
              <input
                value={(state.filters.company?.value as string) ?? ""}
                onChange={(event) =>
                  dispatch({
                    type: "setFilter",
                    key: "company",
                    filter: event.target.value
                      ? { op: "contains", value: event.target.value }
                      : null,
                  })
                }
                aria-label="Filter by company"
                className="h-7 rounded border border-border bg-card px-2 text-xs"
              />
            </label>

            <label className="flex items-center gap-2 text-xs">
              Source
              <input
                value={(state.filters.source?.value as string) ?? ""}
                onChange={(event) =>
                  dispatch({
                    type: "setFilter",
                    key: "source",
                    filter: event.target.value
                      ? { op: "eq", value: event.target.value }
                      : null,
                  })
                }
                placeholder="apollo"
                aria-label="Filter by source"
                className="h-7 w-28 rounded border border-border bg-card px-2 text-xs"
              />
            </label>

            {tags.length > 0 && (
              <label className="flex items-center gap-2 text-xs">
                Tags
                <select
                  multiple
                  size={Math.min(4, tags.length)}
                  value={state.tagIds}
                  onChange={(event) =>
                    dispatch({
                      type: "setTagIds",
                      value: Array.from(
                        event.target.selectedOptions,
                        (option) => option.value,
                      ),
                    })
                  }
                  aria-label="Filter by tag"
                  className="rounded border border-border bg-card px-2 py-1 text-xs"
                >
                  {tags.map((tag) => (
                    <option key={tag.id} value={tag.id}>
                      {tag.name}
                    </option>
                  ))}
                </select>
              </label>
            )}
          </div>

          {filterCount > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 border-t border-border pt-2">
              {Object.entries(state.filters).map(([key, filter]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => dispatch({ type: "setFilter", key, filter: null })}
                  className="flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-xs hover:bg-muted/70"
                  aria-label={`Remove filter: ${describeFilter(key, filter)}`}
                >
                  {describeFilter(key, filter)}
                  <X size={10} aria-hidden="true" />
                </button>
              ))}
              <Button size="sm" variant="ghost" onClick={() => dispatch({ type: "clearFilters" })}>
                Clear all
              </Button>
            </div>
          )}
        </div>
      )}

      {showColumns && (
        <div className="flex flex-wrap gap-3 rounded border border-border bg-card p-3">
          {GRID_COLUMNS.map((column) => {
            const visible =
              state.columns.find((c) => c.key === column.key)?.visible ?? true;
            return (
              <label key={column.key} className="flex items-center gap-1.5 text-xs">
                <input
                  type="checkbox"
                  checked={visible}
                  onChange={() => dispatch({ type: "toggleColumn", key: column.key })}
                  className="h-3.5 w-3.5 accent-[rgb(var(--primary))]"
                />
                {column.label}
              </label>
            );
          })}
        </div>
      )}
    </div>
  );
}

/** Appears only when rows are selected. Fixed to the bottom so it does not
 *  push the grid around as the selection changes. */
export function BulkActionBar({
  count,
  tags,
  onStatus,
  onAddTag,
  onRemoveTag,
  onExport,
  onClear,
  busy,
}: {
  count: number;
  tags: CrmTag[];
  onStatus: (status: LeadStatus) => void;
  onAddTag: (tagId: string) => void;
  onRemoveTag: (tagId: string) => void;
  onExport: () => void;
  onClear: () => void;
  busy: boolean;
}) {
  if (count === 0) return null;

  return (
    <div
      role="region"
      aria-label="Bulk actions"
      className="sticky bottom-4 z-20 mx-auto flex w-fit max-w-full flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-2 shadow-lg"
    >
      <span className="px-1 text-sm font-medium tabular-nums">
        {count} selected
      </span>

      <select
        defaultValue=""
        disabled={busy}
        onChange={(event) => {
          if (event.target.value) {
            onStatus(event.target.value as LeadStatus);
            event.target.value = "";
          }
        }}
        aria-label="Set status for selected leads"
        className="h-8 rounded border border-border bg-card px-2 text-xs"
      >
        <option value="">Set status…</option>
        {STATUSES.map((status) => (
          <option key={status} value={status}>
            {status.replace(/_/g, " ")}
          </option>
        ))}
      </select>

      {tags.length > 0 && (
        <>
          <select
            defaultValue=""
            disabled={busy}
            onChange={(event) => {
              if (event.target.value) {
                onAddTag(event.target.value);
                event.target.value = "";
              }
            }}
            aria-label="Add tag to selected leads"
            className="h-8 rounded border border-border bg-card px-2 text-xs"
          >
            <option value="">Add tag…</option>
            {tags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
          <select
            defaultValue=""
            disabled={busy}
            onChange={(event) => {
              if (event.target.value) {
                onRemoveTag(event.target.value);
                event.target.value = "";
              }
            }}
            aria-label="Remove tag from selected leads"
            className="h-8 rounded border border-border bg-card px-2 text-xs"
          >
            <option value="">Remove tag…</option>
            {tags.map((tag) => (
              <option key={tag.id} value={tag.id}>
                {tag.name}
              </option>
            ))}
          </select>
        </>
      )}

      <Button size="sm" variant="outline" onClick={onExport}>
        <Download size={14} aria-hidden="true" />
        Export selected
      </Button>
      <Button size="sm" variant="ghost" onClick={onClear}>
        Clear
      </Button>
    </div>
  );
}
