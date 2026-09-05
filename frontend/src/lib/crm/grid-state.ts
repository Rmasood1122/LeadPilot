/** M9 data grid — pure state logic.
 *
 * Everything the grid does that is not rendering: column layout, sort,
 * filters, selection, saved-view round-tripping, CSV export. Kept as pure
 * functions over a plain state object so it can be unit-tested without
 * mounting a component or a query client.
 *
 * NOTE ON WHERE SORTING AND FILTERING HAPPEN: not here. These reducers
 * describe the QUERY — which the server executes over the full result set.
 * Sorting a page of 100 rows in the browser would order that page and leave
 * the other 4,900 rows where they were, which is worse than not sorting at
 * all because it looks like it worked.
 */

import { ALLOWED_TRANSITIONS } from "@/lib/api/leads";
import type {
  CrmColumnState,
  CrmFilter,
  CrmFilterOp,
  CrmGridRow,
  CrmSavedView,
  CrmSort,
  LeadStatus,
} from "@/lib/api/types";

export interface GridColumnDef {
  key: string;
  label: string;
  /** Server-side sortable. A column the backend's allow-list does not know
   *  about cannot be sorted, and the header must not offer it. */
  sortable: boolean;
  filterable: boolean;
  editable: boolean;
  defaultWidth: number;
  /** Rendered right-aligned (counts) rather than left (text). */
  numeric?: boolean;
}

/** The built-in columns. Keys match app/services/crm_service.py::GRID_COLUMNS
 *  for the sortable/filterable ones — a key this side that the server does not
 *  know is silently ignored there, so the two lists are kept aligned by hand
 *  and by src/tests/crm-grid-state.test.ts. */
export const GRID_COLUMNS: GridColumnDef[] = [
  { key: "full_name", label: "Name", sortable: true, filterable: true, editable: false, defaultWidth: 200 },
  { key: "company", label: "Company", sortable: true, filterable: true, editable: false, defaultWidth: 200 },
  { key: "title", label: "Title", sortable: true, filterable: true, editable: false, defaultWidth: 180 },
  { key: "email", label: "Email", sortable: true, filterable: true, editable: false, defaultWidth: 240 },
  { key: "status", label: "Status", sortable: true, filterable: true, editable: true, defaultWidth: 150 },
  { key: "tags", label: "Tags", sortable: false, filterable: false, editable: true, defaultWidth: 200 },
  { key: "priority", label: "Priority", sortable: false, filterable: false, editable: true, defaultWidth: 120 },
  { key: "owner_user_id", label: "Owner", sortable: false, filterable: false, editable: true, defaultWidth: 140 },
  { key: "note_count", label: "Notes", sortable: false, filterable: false, editable: false, defaultWidth: 90, numeric: true },
  { key: "source", label: "Source", sortable: true, filterable: true, editable: false, defaultWidth: 120 },
  { key: "created_at", label: "Created", sortable: true, filterable: false, editable: false, defaultWidth: 140 },
];

export const MIN_COLUMN_WIDTH = 80;
export const MAX_COLUMN_WIDTH = 640;

export interface GridState {
  /** Ordered — this array IS the column order. */
  columns: CrmColumnState[];
  sort: CrmSort[];
  filters: Record<string, CrmFilter>;
  search: string;
  tagIds: string[];
  selected: Set<string>;
  offset: number;
  limit: number;
  /** The saved view currently loaded, if any. */
  viewId: string | null;
  viewName: string | null;
  /** True when the state has diverged from the loaded view — drives the
   *  "unsaved changes" affordance, so a user does not lose a filter set they
   *  thought was saved. */
  dirty: boolean;
}

export function defaultColumns(): CrmColumnState[] {
  return GRID_COLUMNS.map((column) => ({
    key: column.key,
    width: column.defaultWidth,
    visible: true,
  }));
}

export function initialGridState(limit = 100): GridState {
  return {
    columns: defaultColumns(),
    sort: [{ key: "created_at", dir: "desc" }],
    filters: {},
    search: "",
    tagIds: [],
    selected: new Set(),
    offset: 0,
    limit,
    viewId: null,
    viewName: null,
    dirty: false,
  };
}

export type GridAction =
  | { type: "toggleSort"; key: string; additive: boolean }
  | { type: "setFilter"; key: string; filter: CrmFilter | null }
  | { type: "clearFilters" }
  | { type: "setSearch"; value: string }
  | { type: "setTagIds"; value: string[] }
  | { type: "resizeColumn"; key: string; width: number }
  | { type: "moveColumn"; key: string; toIndex: number }
  | { type: "toggleColumn"; key: string }
  | { type: "selectRow"; id: string; selected: boolean }
  | { type: "selectRange"; ids: string[] }
  | { type: "selectAll"; ids: string[] }
  | { type: "clearSelection" }
  | { type: "setOffset"; offset: number }
  | { type: "loadView"; view: CrmSavedView }
  | { type: "viewSaved"; view: CrmSavedView }
  | { type: "resetView" };

/** Marks the state dirty relative to its loaded saved view.
 *
 *  Only applied to the things a view actually stores (columns, sort,
 *  filters). Selection and paging are session state, not part of a view, so
 *  ticking a checkbox must not light up "unsaved changes". */
function touched(state: GridState): GridState {
  return state.viewId ? { ...state, dirty: true } : state;
}

export function gridReducer(state: GridState, action: GridAction): GridState {
  switch (action.type) {
    case "toggleSort": {
      const existing = state.sort.find((s) => s.key === action.key);
      let sort: CrmSort[];
      if (!action.additive) {
        // Plain click: this column becomes the only sort. asc -> desc -> off,
        // so a third click clears rather than trapping the user in a sort
        // they cannot undo without reloading.
        if (!existing) sort = [{ key: action.key, dir: "asc" }];
        else if (existing.dir === "asc") sort = [{ key: action.key, dir: "desc" }];
        else sort = [];
      } else {
        // Shift-click: add to / cycle within the existing multi-sort, keeping
        // the order the user added them in — that order is the precedence.
        if (!existing) {
          sort = [...state.sort, { key: action.key, dir: "asc" }];
        } else if (existing.dir === "asc") {
          sort = state.sort.map((s) =>
            s.key === action.key ? { ...s, dir: "desc" as const } : s,
          );
        } else {
          sort = state.sort.filter((s) => s.key !== action.key);
        }
      }
      // Any sort change invalidates the current page offset: page 3 of the
      // old order is meaningless in the new one.
      return touched({ ...state, sort, offset: 0 });
    }

    case "setFilter": {
      const filters = { ...state.filters };
      if (action.filter === null) delete filters[action.key];
      else filters[action.key] = action.filter;
      return touched({ ...state, filters, offset: 0, selected: new Set() });
    }

    case "clearFilters":
      return touched({
        ...state,
        filters: {},
        search: "",
        tagIds: [],
        offset: 0,
        selected: new Set(),
      });

    case "setSearch":
      return { ...state, search: action.value, offset: 0, selected: new Set() };

    case "setTagIds":
      return touched({
        ...state,
        tagIds: action.value,
        offset: 0,
        selected: new Set(),
      });

    case "resizeColumn": {
      const width = Math.max(
        MIN_COLUMN_WIDTH,
        Math.min(MAX_COLUMN_WIDTH, Math.round(action.width)),
      );
      return touched({
        ...state,
        columns: state.columns.map((c) =>
          c.key === action.key ? { ...c, width } : c,
        ),
      });
    }

    case "moveColumn": {
      const from = state.columns.findIndex((c) => c.key === action.key);
      if (from === -1) return state;
      const columns = [...state.columns];
      const [moved] = columns.splice(from, 1);
      const to = Math.max(0, Math.min(columns.length, action.toIndex));
      columns.splice(to, 0, moved);
      return touched({ ...state, columns });
    }

    case "toggleColumn": {
      const columns = state.columns.map((c) =>
        c.key === action.key ? { ...c, visible: !c.visible } : c,
      );
      // Never let the grid become a blank rectangle with no way back.
      if (!columns.some((c) => c.visible)) return state;
      return touched({ ...state, columns });
    }

    case "selectRow": {
      const selected = new Set(state.selected);
      if (action.selected) selected.add(action.id);
      else selected.delete(action.id);
      return { ...state, selected };
    }

    case "selectRange": {
      const selected = new Set(state.selected);
      for (const id of action.ids) selected.add(id);
      return { ...state, selected };
    }

    case "selectAll": {
      // Toggle semantics: if everything on the page is already selected, the
      // header checkbox clears it. A checkbox that only ever selects is a
      // checkbox that looks broken on the second click.
      const allSelected =
        action.ids.length > 0 && action.ids.every((id) => state.selected.has(id));
      if (allSelected) {
        const selected = new Set(state.selected);
        for (const id of action.ids) selected.delete(id);
        return { ...state, selected };
      }
      const selected = new Set(state.selected);
      for (const id of action.ids) selected.add(id);
      return { ...state, selected };
    }

    case "clearSelection":
      return { ...state, selected: new Set() };

    case "setOffset":
      return { ...state, offset: Math.max(0, action.offset) };

    case "loadView":
      return {
        ...state,
        columns: mergeColumns(action.view.columns_json),
        sort: action.view.sort_json ?? [],
        filters: action.view.filters_json ?? {},
        offset: 0,
        selected: new Set(),
        viewId: action.view.id,
        viewName: action.view.name,
        dirty: false,
      };

    case "viewSaved":
      return {
        ...state,
        viewId: action.view.id,
        viewName: action.view.name,
        dirty: false,
      };

    case "resetView":
      return { ...initialGridState(state.limit) };

    default:
      return state;
  }
}

/** Reconcile a stored column layout against the columns that exist NOW.
 *
 *  A view saved before a column was added would otherwise hide it forever
 *  (it is simply absent from columns_json), and a view saved before one was
 *  removed would render a header with nothing under it. So: keep the stored
 *  order and widths for columns that still exist, append any new ones at the
 *  end, drop any that are gone. */
export function mergeColumns(stored: CrmColumnState[]): CrmColumnState[] {
  const known = new Map(GRID_COLUMNS.map((c) => [c.key, c]));
  const merged: CrmColumnState[] = [];
  const seen = new Set<string>();

  for (const column of stored ?? []) {
    const def = known.get(column.key);
    if (!def) continue; // column no longer exists
    merged.push({
      key: column.key,
      width: Math.max(
        MIN_COLUMN_WIDTH,
        Math.min(MAX_COLUMN_WIDTH, column.width || def.defaultWidth),
      ),
      visible: column.visible !== false,
    });
    seen.add(column.key);
  }

  for (const def of GRID_COLUMNS) {
    if (!seen.has(def.key)) {
      merged.push({ key: def.key, width: def.defaultWidth, visible: true });
    }
  }
  return merged;
}

/** The part of the state a saved view persists. Selection, paging and the
 *  free-text search are session state and deliberately excluded — a saved
 *  view is a lens, not a bookmark of what you had highlighted. */
export function toSavedViewInput(state: GridState, name: string, isDefault: boolean) {
  return {
    name,
    view_type: "grid" as const,
    filters_json: state.filters,
    sort_json: state.sort,
    columns_json: state.columns,
    is_default: isDefault,
  };
}

export function visibleColumns(state: GridState): GridColumnDef[] {
  const known = new Map(GRID_COLUMNS.map((c) => [c.key, c]));
  return state.columns
    .filter((c) => c.visible)
    .map((c) => known.get(c.key))
    .filter((c): c is GridColumnDef => !!c);
}

export function columnWidth(state: GridState, key: string): number {
  return (
    state.columns.find((c) => c.key === key)?.width ??
    GRID_COLUMNS.find((c) => c.key === key)?.defaultWidth ??
    160
  );
}

export function sortDirection(state: GridState, key: string): "asc" | "desc" | null {
  return state.sort.find((s) => s.key === key)?.dir ?? null;
}

/** 1-based position of a column within a multi-sort, for the header badge.
 *  null when it is not part of the sort, or when the sort is single-column
 *  (a lone "1" badge is noise). */
export function sortRank(state: GridState, key: string): number | null {
  if (state.sort.length < 2) return null;
  const index = state.sort.findIndex((s) => s.key === key);
  return index === -1 ? null : index + 1;
}

// --------------------------------------------------------------------------
// Filter helpers
// --------------------------------------------------------------------------

export const FILTER_OPS: { op: CrmFilterOp; label: string }[] = [
  { op: "contains", label: "contains" },
  { op: "eq", label: "is" },
  { op: "in", label: "is any of" },
  { op: "not_in", label: "is none of" },
  { op: "is_empty", label: "is empty" },
  { op: "is_not_empty", label: "is not empty" },
];

export function describeFilter(key: string, filter: CrmFilter): string {
  const label = GRID_COLUMNS.find((c) => c.key === key)?.label ?? key;
  const op = FILTER_OPS.find((o) => o.op === filter.op)?.label ?? filter.op;
  if (filter.op === "is_empty" || filter.op === "is_not_empty") {
    return `${label} ${op}`;
  }
  const value = Array.isArray(filter.value)
    ? filter.value.join(", ")
    : String(filter.value ?? "");
  return `${label} ${op} ${value}`;
}

export function activeFilterCount(state: GridState): number {
  return (
    Object.keys(state.filters).length +
    (state.search ? 1 : 0) +
    (state.tagIds.length ? 1 : 0)
  );
}

// --------------------------------------------------------------------------
// CSV export — ONE WAY, download only
// --------------------------------------------------------------------------

/** Serialise rows to CSV text.
 *
 *  Export only. There is no import, and no "edit the CSV and paste it back":
 *  the grid IS the editing surface, and a spreadsheet round trip is exactly
 *  the thing this feature was built to replace.
 *
 *  Fields are quoted and inner quotes doubled per RFC 4180. A leading =, +,
 *  - or @ is prefixed with a single quote: Excel and Sheets treat those as
 *  the start of a formula, so a company literally named "=SUM" would execute
 *  on open. That is CSV injection, and it is the export side's job to
 *  prevent it. */
export function toCsvValue(value: unknown): string {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (/^[=+\-@\t\r]/.test(text)) text = `'${text}`;
  if (/[",\n\r]/.test(text)) text = `"${text.replace(/"/g, '""')}"`;
  return text;
}

export function rowsToCsv(rows: CrmGridRow[], columns: GridColumnDef[]): string {
  const header = columns.map((c) => toCsvValue(c.label)).join(",");
  const body = rows.map((row) =>
    columns
      .map((column) => {
        const raw = (row as unknown as Record<string, unknown>)[column.key];
        if (column.key === "tags") {
          return toCsvValue(row.tags.map((t) => t.name).join(" | "));
        }
        return toCsvValue(raw);
      })
      .join(","),
  );
  return [header, ...body].join("\r\n");
}

// --------------------------------------------------------------------------
// Keyboard navigation
// --------------------------------------------------------------------------

export interface CellCursor {
  row: number;
  col: number;
}

/** Move the cursor within the grid. Clamps at the edges rather than wrapping:
 *  wrapping from the last column of row 3 to the first of row 4 is what a
 *  spreadsheet does with Tab, but arrow keys that teleport across rows are
 *  disorienting. Tab is handled separately by the component. */
export function moveCursor(
  cursor: CellCursor,
  key: string,
  rowCount: number,
  colCount: number,
): CellCursor {
  const clampRow = (n: number) => Math.max(0, Math.min(rowCount - 1, n));
  const clampCol = (n: number) => Math.max(0, Math.min(colCount - 1, n));
  switch (key) {
    case "ArrowUp":
      return { ...cursor, row: clampRow(cursor.row - 1) };
    case "ArrowDown":
      return { ...cursor, row: clampRow(cursor.row + 1) };
    case "ArrowLeft":
      return { ...cursor, col: clampCol(cursor.col - 1) };
    case "ArrowRight":
      return { ...cursor, col: clampCol(cursor.col + 1) };
    case "Home":
      return { ...cursor, col: 0 };
    case "End":
      return { ...cursor, col: clampCol(colCount - 1) };
    case "PageUp":
      return { ...cursor, row: clampRow(cursor.row - 10) };
    case "PageDown":
      return { ...cursor, row: clampRow(cursor.row + 10) };
    default:
      return cursor;
  }
}

/** Tab advances by cell and wraps onto the next row, like a spreadsheet.
 *  Returns null at the very end so the caller can let focus leave the grid
 *  rather than trapping it. */
export function tabCursor(
  cursor: CellCursor,
  rowCount: number,
  colCount: number,
  backwards: boolean,
): CellCursor | null {
  const flat = cursor.row * colCount + cursor.col + (backwards ? -1 : 1);
  if (flat < 0 || flat >= rowCount * colCount) return null;
  return { row: Math.floor(flat / colCount), col: flat % colCount };
}

// --------------------------------------------------------------------------
// Inline edit validation (mirrors the server; the server is authoritative)
// --------------------------------------------------------------------------

/** The transition map is NOT redefined here.
 *
 *  src/lib/api/leads.ts owns the frontend copy and the kanban already uses
 *  it; the backend re-validates against app/api/ui_support.py's map. Three
 *  copies would be three things to update, and the first time they disagree
 *  the same move is offered on one screen and rejected on another. */
export { ALLOWED_TRANSITIONS, canTransition } from "@/lib/api/leads";

/** What a status cell's dropdown offers: the current value (so the select
 *  can render it) plus every legal move from it. */
export function statusOptionsFor(current: LeadStatus): LeadStatus[] {
  return [current, ...(ALLOWED_TRANSITIONS[current] ?? [])];
}
