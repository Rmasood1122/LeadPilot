"use client";

/** The data grid: a spreadsheet-shaped view of leads, built from scratch.
 *
 * NO SPREADSHEET LIBRARY. Not SheetJS, not an embedded Sheet, not a CSV round
 * trip. The grid IS the editing surface; CSV leaves as a download and never
 * comes back. That constraint is the point of the feature — an export/edit/
 * import loop means every edit is stale the moment it is made, and two people
 * working the same list silently overwrite each other.
 *
 * WHAT MAKES IT FAST AT 5,000+ ROWS
 *   * the server pages, sorts and filters (see crm_service.grid_page) — the
 *     browser never holds the whole set;
 *   * rows are virtualized (useVirtualRows), so a page of 200 renders ~30
 *     DOM rows;
 *   * every row is a fixed height, which is what makes the virtualization
 *     arithmetic rather than measurement.
 *
 * ACCESSIBILITY: this is a real `role="grid"` with `aria-rowindex` /
 * `aria-colindex` on virtualized cells, because the rendered DOM is a window
 * into a larger set and a screen reader has no other way to know that.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, ChevronUp, StickyNote } from "lucide-react";

import type {
  CrmGridRow,
  CrmTag,
  FollowupStatus,
  LeadStatus,
} from "@/lib/api/types";
import {
  type CellCursor,
  type GridAction,
  type GridState,
  columnWidth,
  moveCursor,
  sortDirection,
  sortRank,
  statusOptionsFor,
  tabCursor,
  visibleColumns,
} from "@/lib/crm/grid-state";
import { useVirtualRows } from "@/lib/crm/useVirtualRows";
import { Badge, statusTone } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const ROW_HEIGHT = 36;
const HEADER_HEIGHT = 36;
const SELECT_COLUMN_WIDTH = 40;

export interface DataGridProps {
  rows: CrmGridRow[];
  state: GridState;
  dispatch: (action: GridAction) => void;
  /** Absolute row index of the first row on this page, for aria-rowindex. */
  pageOffset: number;
  /** Total rows across all pages, for aria-rowcount. */
  totalRows: number;
  onEdit: (leadId: string, patch: Record<string, unknown>) => void;
  onOpenNotes: (leadId: string) => void;
  isFetching: boolean;
}

export function DataGrid({
  rows,
  state,
  dispatch,
  pageOffset,
  totalRows,
  onEdit,
  onOpenNotes,
  isFetching,
}: DataGridProps) {
  const columns = useMemo(() => visibleColumns(state), [state]);
  const [cursor, setCursor] = useState<CellCursor>({ row: 0, col: 0 });
  const [editing, setEditing] = useState<CellCursor | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const { scrollRef, onScroll, scrollToRow, window: vwindow } = useVirtualRows({
    rowCount: rows.length,
    rowHeight: ROW_HEIGHT,
  });

  // A shorter result set (a filter was applied) can leave the cursor pointing
  // past the end, which makes keyboard navigation appear dead.
  useEffect(() => {
    if (cursor.row > Math.max(0, rows.length - 1)) {
      setCursor((current) => ({ ...current, row: Math.max(0, rows.length - 1) }));
    }
  }, [rows.length, cursor.row]);

  const commit = useCallback(
    (row: CrmGridRow, key: string, value: unknown) => {
      setEditing(null);
      containerRef.current?.focus();
      onEdit(row.id, { [key]: value });
    },
    [onEdit],
  );

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      // While a cell editor is open it owns the keyboard entirely — Escape
      // and Enter are handled there, and arrow keys must move the caret
      // inside the input rather than the cursor across the grid.
      if (editing) return;

      const key = event.key;
      const columnCount = columns.length;

      if (key === "Tab") {
        const next = tabCursor(cursor, rows.length, columnCount, event.shiftKey);
        // null means the edge — let focus leave rather than trapping it.
        if (next === null) return;
        event.preventDefault();
        setCursor(next);
        scrollToRow(next.row);
        return;
      }

      if (
        ["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Home", "End", "PageUp", "PageDown"].includes(key)
      ) {
        event.preventDefault();
        const next = moveCursor(cursor, key, rows.length, columnCount);
        setCursor(next);
        scrollToRow(next.row);
        return;
      }

      if (key === "Enter") {
        event.preventDefault();
        const column = columns[cursor.col];
        if (column?.editable) setEditing(cursor);
        return;
      }

      if (key === " " && rows[cursor.row]) {
        event.preventDefault();
        const row = rows[cursor.row];
        dispatch({
          type: "selectRow",
          id: row.id,
          selected: !state.selected.has(row.id),
        });
      }
    },
    [columns, cursor, dispatch, editing, rows, scrollToRow, state.selected],
  );

  const pageIds = useMemo(() => rows.map((row) => row.id), [rows]);
  const allSelected =
    pageIds.length > 0 && pageIds.every((id) => state.selected.has(id));

  const gridWidth =
    SELECT_COLUMN_WIDTH +
    columns.reduce((total, column) => total + columnWidth(state, column.key), 0);

  return (
    <div
      ref={containerRef}
      role="grid"
      aria-label="Leads"
      aria-rowcount={totalRows + 1}
      aria-colcount={columns.length + 1}
      aria-busy={isFetching}
      tabIndex={0}
      onKeyDown={onKeyDown}
      className="rounded border border-border bg-card focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
    >
      <div
        ref={scrollRef}
        onScroll={onScroll}
        className="max-h-[60vh] overflow-auto"
      >
        <div style={{ width: gridWidth, minWidth: "100%" }}>
          <GridHeader
            columns={columns}
            state={state}
            dispatch={dispatch}
            allSelected={allSelected}
            pageIds={pageIds}
          />

          {/* Spacer sized to the FULL list so the scrollbar is honest, with
              only the visible slice rendered inside it. */}
          <div style={{ height: vwindow.totalHeight, position: "relative" }}>
            <div
              style={{
                transform: `translateY(${vwindow.offsetY}px)`,
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
              }}
            >
              {rows.slice(vwindow.start, vwindow.end).map((row, index) => {
                const rowIndex = vwindow.start + index;
                return (
                  <GridRow
                    key={row.id}
                    row={row}
                    rowIndex={rowIndex}
                    ariaRowIndex={pageOffset + rowIndex + 2}
                    columns={columns}
                    state={state}
                    dispatch={dispatch}
                    cursor={cursor}
                    setCursor={setCursor}
                    editing={editing}
                    setEditing={setEditing}
                    commit={commit}
                    onOpenNotes={onOpenNotes}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GridHeader({
  columns,
  state,
  dispatch,
  allSelected,
  pageIds,
}: {
  columns: ReturnType<typeof visibleColumns>;
  state: GridState;
  dispatch: (action: GridAction) => void;
  allSelected: boolean;
  pageIds: string[];
}) {
  return (
    <div
      role="row"
      aria-rowindex={1}
      className="sticky top-0 z-10 flex border-b border-border bg-muted/60 backdrop-blur"
      style={{ height: HEADER_HEIGHT }}
    >
      <div
        role="columnheader"
        aria-colindex={1}
        className="flex shrink-0 items-center justify-center"
        style={{ width: SELECT_COLUMN_WIDTH }}
      >
        <input
          type="checkbox"
          checked={allSelected}
          onChange={() => dispatch({ type: "selectAll", ids: pageIds })}
          aria-label={allSelected ? "Deselect all rows on this page" : "Select all rows on this page"}
          className="h-3.5 w-3.5 accent-[rgb(var(--primary))]"
        />
      </div>

      {columns.map((column, index) => {
        const direction = sortDirection(state, column.key);
        const rank = sortRank(state, column.key);
        return (
          <div
            key={column.key}
            role="columnheader"
            aria-colindex={index + 2}
            aria-sort={
              direction === "asc"
                ? "ascending"
                : direction === "desc"
                  ? "descending"
                  : column.sortable
                    ? "none"
                    : undefined
            }
            className="group relative flex shrink-0 items-center border-r border-border/60 px-2 text-xs font-medium"
            style={{ width: columnWidth(state, column.key) }}
          >
            <button
              type="button"
              disabled={!column.sortable}
              onClick={(event) =>
                column.sortable &&
                dispatch({
                  type: "toggleSort",
                  key: column.key,
                  // Shift-click builds a multi-column sort; the order the
                  // user adds them in is the precedence.
                  additive: event.shiftKey,
                })
              }
              title={
                column.sortable
                  ? "Click to sort. Shift-click to add to the sort."
                  : "This column cannot be sorted"
              }
              className={cn(
                "flex min-w-0 flex-1 items-center gap-1 truncate text-left",
                column.sortable ? "cursor-pointer hover:text-foreground" : "cursor-default",
                column.numeric && "justify-end",
              )}
            >
              <span className="truncate">{column.label}</span>
              {direction === "asc" && <ChevronUp size={12} aria-hidden="true" />}
              {direction === "desc" && <ChevronDown size={12} aria-hidden="true" />}
              {rank !== null && (
                <span className="text-[10px] text-muted-foreground" aria-hidden="true">
                  {rank}
                </span>
              )}
            </button>

            <ColumnResizer
              onResize={(width) =>
                dispatch({ type: "resizeColumn", key: column.key, width })
              }
              startWidth={columnWidth(state, column.key)}
              label={column.label}
            />
          </div>
        );
      })}
    </div>
  );
}

/** Drag handle on a column's right edge.
 *
 *  Listeners go on `window` for the duration of the drag, not on the handle:
 *  the pointer routinely leaves a 4px-wide element while dragging fast, and a
 *  handle-scoped mousemove drops the drag the moment it does. */
function ColumnResizer({
  onResize,
  startWidth,
  label,
}: {
  onResize: (width: number) => void;
  startWidth: number;
  label: string;
}) {
  const drag = useRef<{ x: number; width: number } | null>(null);

  const onPointerDown = (event: React.PointerEvent) => {
    event.preventDefault();
    event.stopPropagation(); // never let a resize also trigger the sort
    drag.current = { x: event.clientX, width: startWidth };

    const onMove = (move: PointerEvent) => {
      if (!drag.current) return;
      onResize(drag.current.width + (move.clientX - drag.current.x));
    };
    const onUp = () => {
      drag.current = null;
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <span
      role="separator"
      aria-orientation="vertical"
      aria-label={`Resize ${label} column`}
      onPointerDown={onPointerDown}
      className="absolute right-0 top-0 h-full w-1 cursor-col-resize bg-transparent hover:bg-[rgb(var(--primary))]/40"
    />
  );
}

function GridRow({
  row,
  rowIndex,
  ariaRowIndex,
  columns,
  state,
  dispatch,
  cursor,
  setCursor,
  editing,
  setEditing,
  commit,
  onOpenNotes,
}: {
  row: CrmGridRow;
  rowIndex: number;
  ariaRowIndex: number;
  columns: ReturnType<typeof visibleColumns>;
  state: GridState;
  dispatch: (action: GridAction) => void;
  cursor: CellCursor;
  setCursor: (cursor: CellCursor) => void;
  editing: CellCursor | null;
  setEditing: (cursor: CellCursor | null) => void;
  commit: (row: CrmGridRow, key: string, value: unknown) => void;
  onOpenNotes: (leadId: string) => void;
}) {
  const selected = state.selected.has(row.id);

  return (
    <div
      role="row"
      aria-rowindex={ariaRowIndex}
      aria-selected={selected}
      className={cn(
        "flex border-b border-border/50",
        selected ? "bg-[rgb(var(--primary))]/10" : "hover:bg-muted/40",
      )}
      style={{ height: ROW_HEIGHT }}
    >
      <div
        role="gridcell"
        aria-colindex={1}
        className="flex shrink-0 items-center justify-center"
        style={{ width: SELECT_COLUMN_WIDTH }}
      >
        <input
          type="checkbox"
          checked={selected}
          onChange={(event) =>
            dispatch({ type: "selectRow", id: row.id, selected: event.target.checked })
          }
          aria-label={`Select ${row.full_name ?? row.email ?? "lead"}`}
          className="h-3.5 w-3.5 accent-[rgb(var(--primary))]"
        />
      </div>

      {columns.map((column, colIndex) => {
        const isCursor = cursor.row === rowIndex && cursor.col === colIndex;
        const isEditing =
          editing?.row === rowIndex && editing?.col === colIndex;
        return (
          <div
            key={column.key}
            role="gridcell"
            aria-colindex={colIndex + 2}
            onMouseDown={() => setCursor({ row: rowIndex, col: colIndex })}
            onDoubleClick={() =>
              column.editable && setEditing({ row: rowIndex, col: colIndex })
            }
            className={cn(
              "flex shrink-0 items-center overflow-hidden border-r border-border/40 px-2 text-sm",
              column.numeric && "justify-end tabular-nums",
              isCursor && "ring-1 ring-inset ring-[rgb(var(--primary))]",
              column.editable && "cursor-text",
            )}
            style={{ width: columnWidth(state, column.key) }}
          >
            <GridCell
              row={row}
              columnKey={column.key}
              editable={column.editable}
              isEditing={isEditing}
              onStartEdit={() => setEditing({ row: rowIndex, col: colIndex })}
              onCancel={() => setEditing(null)}
              onCommit={(value) => commit(row, column.key, value)}
              onOpenNotes={onOpenNotes}
            />
          </div>
        );
      })}
    </div>
  );
}

function GridCell({
  row,
  columnKey,
  editable,
  isEditing,
  onStartEdit,
  onCancel,
  onCommit,
  onOpenNotes,
}: {
  row: CrmGridRow;
  columnKey: string;
  editable: boolean;
  isEditing: boolean;
  onStartEdit: () => void;
  onCancel: () => void;
  onCommit: (value: unknown) => void;
  onOpenNotes: (leadId: string) => void;
}) {
  if (columnKey === "status") {
    if (isEditing) {
      return (
        <StatusEditor
          value={row.status}
          onCancel={onCancel}
          onCommit={(next) => onCommit(next)}
        />
      );
    }
    return (
      <button
        type="button"
        onClick={onStartEdit}
        className="truncate"
        aria-label={`Status: ${row.status}. Click to change.`}
      >
        <Badge tone={statusTone(row.status)}>{row.status.replace(/_/g, " ")}</Badge>
      </button>
    );
  }

  if (columnKey === "tags") {
    return <TagCell tags={row.tags} />;
  }

  if (columnKey === "followup_status") {
    return <FollowupCell status={row.followup_status} />;
  }

  if (columnKey === "note_count") {
    return (
      <button
        type="button"
        onClick={() => onOpenNotes(row.id)}
        className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        aria-label={`${row.note_count} note${row.note_count === 1 ? "" : "s"}. Open notes.`}
      >
        <StickyNote size={12} aria-hidden="true" />
        {row.note_count}
      </button>
    );
  }

  if (columnKey === "priority" && isEditing) {
    return (
      <TextEditor
        value={row.priority ?? ""}
        onCancel={onCancel}
        onCommit={onCommit}
        placeholder="high / medium / low"
      />
    );
  }

  if (columnKey === "owner_user_id") {
    // Team accounts are not built, so ownership is binary: mine or unassigned.
    // A user picker here would imply a capability that does not exist.
    return (
      <button
        type="button"
        onClick={onStartEdit}
        className="truncate text-sm text-muted-foreground hover:text-foreground"
        aria-label={row.owner_user_id ? "Owned by you. Click to unassign." : "Unassigned. Click to claim."}
      >
        {row.owner_user_id ? "You" : "—"}
      </button>
    );
  }

  if (columnKey === "created_at" || columnKey === "next_action_at") {
    const raw = (row as unknown as Record<string, string | null>)[columnKey];
    return (
      <span className="truncate text-muted-foreground" title={raw ?? undefined}>
        {raw ? new Date(raw).toLocaleDateString() : "—"}
      </span>
    );
  }

  const value = (row as unknown as Record<string, unknown>)[columnKey];
  const text = value === null || value === undefined || value === "" ? "—" : String(value);

  if (editable && isEditing) {
    return <TextEditor value={text === "—" ? "" : text} onCancel={onCancel} onCommit={onCommit} />;
  }

  return (
    <span
      className={cn("truncate", text === "—" && "text-muted-foreground")}
      title={text}
    >
      {text}
    </span>
  );
}

/** Engagement Hub, Feature 1 — the follow-up badge.
 *
 *  Five states, three of which the user acts on. "waiting" and "none" render
 *  as a dash rather than a badge: a grid where every row is wearing a chip is
 *  a grid where the chips have stopped meaning anything, and neither of those
 *  states is something to do. The value is computed server-side (see
 *  crm_service.followup_status_for_leads) — the row does not carry the
 *  messages, outcomes and step delays the answer depends on. */
function FollowupCell({ status }: { status: FollowupStatus }) {
  const presentation: Partial<
    Record<FollowupStatus, { label: string; tone: "success" | "warning" | "accent" }>
  > = {
    replied: { label: "Replied", tone: "success" },
    due: { label: "Follow-up due", tone: "warning" },
    scheduled: { label: "Scheduled", tone: "accent" },
  };
  const shown = presentation[status];
  if (!shown) {
    return (
      <span className="text-muted-foreground" title={`Follow-up: ${status}`}>
        —
      </span>
    );
  }
  return (
    <Badge tone={shown.tone} className="truncate">
      {shown.label}
    </Badge>
  );
}

function TagCell({ tags }: { tags: CrmTag[] }) {
  if (tags.length === 0) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <span className="flex gap-1 overflow-hidden">
      {tags.map((tag) => (
        <Badge
          key={tag.id}
          // The token comes from the server as a THEME TOKEN name, never a
          // hex, so a tag recolors with the rest of the app.
          tone={tag.color_token as "default"}
          className="shrink-0"
        >
          {tag.name}
        </Badge>
      ))}
    </span>
  );
}

/** Status dropdown, offering only LEGAL transitions.
 *
 *  The same map the kanban uses and the backend re-validates. Offering a move
 *  the server will reject is a 422 the user cannot act on. */
function StatusEditor({
  value,
  onCancel,
  onCommit,
}: {
  value: LeadStatus;
  onCancel: () => void;
  onCommit: (next: LeadStatus) => void;
}) {
  const options = statusOptionsFor(value);
  return (
    <select
      autoFocus
      defaultValue={value}
      onBlur={onCancel}
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.stopPropagation();
          onCancel();
        }
      }}
      onChange={(event) => {
        const next = event.target.value as LeadStatus;
        if (next === value) onCancel();
        else onCommit(next);
      }}
      aria-label="Change status"
      className="w-full rounded border border-border bg-card px-1 py-0.5 text-xs"
    >
      {options.map((option) => (
        <option key={option} value={option}>
          {option.replace(/_/g, " ")}
        </option>
      ))}
    </select>
  );
}

/** Inline text editor. Enter commits, Escape cancels, blur commits.
 *
 *  Blur-commits rather than blur-cancels because clicking away after typing
 *  reads as "done", not "discard" — losing typed text to a stray click is the
 *  single most irritating thing a grid can do. Escape is the explicit
 *  discard, and it is why keydown stops propagation: the grid's own handler
 *  would otherwise also see it. */
function TextEditor({
  value,
  onCancel,
  onCommit,
  placeholder,
}: {
  value: string;
  onCancel: () => void;
  onCommit: (next: string | null) => void;
  placeholder?: string;
}) {
  const [draft, setDraft] = useState(value);
  const cancelled = useRef(false);

  return (
    <input
      autoFocus
      value={draft}
      placeholder={placeholder}
      onChange={(event) => setDraft(event.target.value)}
      onKeyDown={(event) => {
        event.stopPropagation();
        if (event.key === "Enter") {
          event.preventDefault();
          onCommit(draft === "" ? null : draft);
        } else if (event.key === "Escape") {
          event.preventDefault();
          cancelled.current = true;
          onCancel();
        }
      }}
      onBlur={() => {
        if (cancelled.current) return;
        if (draft === value) onCancel();
        else onCommit(draft === "" ? null : draft);
      }}
      aria-label="Edit cell"
      className="w-full rounded border border-border bg-card px-1 py-0.5 text-sm"
    />
  );
}
