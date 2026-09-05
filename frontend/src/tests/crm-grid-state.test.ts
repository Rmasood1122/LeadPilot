/** M9 data grid — the pure state logic.
 *
 * These reducers are where the grid's behaviour actually lives, so this is
 * where the behaviour is pinned: sort cycling, filter/offset interaction,
 * column layout, selection, saved-view round-tripping, CSV escaping and
 * keyboard movement.
 *
 * Deliberately no rendering. Mounting the grid to assert that a third click
 * clears the sort tests React, jsdom and the reducer at once, and tells you
 * which of the three broke only after you go and look.
 */

import { describe, expect, it } from "vitest";

import {
  GRID_COLUMNS,
  MAX_COLUMN_WIDTH,
  MIN_COLUMN_WIDTH,
  activeFilterCount,
  columnWidth,
  defaultColumns,
  describeFilter,
  gridReducer,
  initialGridState,
  mergeColumns,
  moveCursor,
  rowsToCsv,
  sortDirection,
  sortRank,
  statusOptionsFor,
  tabCursor,
  toCsvValue,
  toSavedViewInput,
  visibleColumns,
} from "@/lib/crm/grid-state";
import { computeWindow } from "@/lib/crm/useVirtualRows";
import type { CrmGridRow, CrmSavedView } from "@/lib/api/types";

const state0 = () => initialGridState(100);

describe("sorting", () => {
  it("cycles asc -> desc -> off on repeated clicks", () => {
    let state = state0();
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    expect(sortDirection(state, "company")).toBe("asc");

    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    expect(sortDirection(state, "company")).toBe("desc");

    // The third click clears it. Without this the user is stuck in a sort
    // they cannot undo without reloading the page.
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    expect(state.sort).toEqual([]);
  });

  it("replaces the sort on a plain click", () => {
    let state = state0();
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    state = gridReducer(state, { type: "toggleSort", key: "email", additive: false });
    expect(state.sort).toEqual([{ key: "email", dir: "asc" }]);
  });

  it("builds a multi-column sort on shift-click, in click order", () => {
    let state = state0();
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    state = gridReducer(state, { type: "toggleSort", key: "full_name", additive: true });
    expect(state.sort).toEqual([
      { key: "company", dir: "asc" },
      { key: "full_name", dir: "asc" },
    ]);
    // Precedence is the order they were added, and the header badge shows it.
    expect(sortRank(state, "company")).toBe(1);
    expect(sortRank(state, "full_name")).toBe(2);
  });

  it("removes one column from a multi-sort without disturbing the rest", () => {
    let state = state0();
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    state = gridReducer(state, { type: "toggleSort", key: "full_name", additive: true });
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: true }); // -> desc
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: true }); // -> off
    expect(state.sort).toEqual([{ key: "full_name", dir: "asc" }]);
  });

  it("shows no rank badge for a single-column sort", () => {
    let state = state0();
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    expect(sortRank(state, "company")).toBeNull();
  });

  it("resets the page offset — page 3 of the old order means nothing", () => {
    let state = gridReducer(state0(), { type: "setOffset", offset: 200 });
    state = gridReducer(state, { type: "toggleSort", key: "company", additive: false });
    expect(state.offset).toBe(0);
  });
});

describe("filters", () => {
  it("sets, replaces and clears a single filter", () => {
    let state = state0();
    state = gridReducer(state, {
      type: "setFilter",
      key: "status",
      filter: { op: "in", value: ["verified"] },
    });
    expect(state.filters.status).toEqual({ op: "in", value: ["verified"] });

    state = gridReducer(state, { type: "setFilter", key: "status", filter: null });
    expect(state.filters.status).toBeUndefined();
  });

  it("clears the selection when the result set changes", () => {
    // A selection of rows that a new filter excludes is a bulk action aimed
    // at rows the user can no longer see.
    let state = gridReducer(state0(), { type: "selectRow", id: "a", selected: true });
    expect(state.selected.size).toBe(1);
    state = gridReducer(state, {
      type: "setFilter",
      key: "company",
      filter: { op: "contains", value: "acme" },
    });
    expect(state.selected.size).toBe(0);
  });

  it("counts search and tags alongside column filters", () => {
    let state = state0();
    expect(activeFilterCount(state)).toBe(0);
    state = gridReducer(state, { type: "setSearch", value: "ada" });
    state = gridReducer(state, { type: "setTagIds", value: ["t1"] });
    state = gridReducer(state, {
      type: "setFilter",
      key: "company",
      filter: { op: "contains", value: "acme" },
    });
    expect(activeFilterCount(state)).toBe(3);
  });

  it("clearFilters clears search and tags too", () => {
    let state = gridReducer(state0(), { type: "setSearch", value: "ada" });
    state = gridReducer(state, { type: "setTagIds", value: ["t1"] });
    state = gridReducer(state, { type: "clearFilters" });
    expect(activeFilterCount(state)).toBe(0);
  });

  it("describes a filter in words for the removable chip", () => {
    expect(describeFilter("company", { op: "contains", value: "acme" })).toBe(
      "Company contains acme",
    );
    expect(describeFilter("status", { op: "in", value: ["a", "b"] })).toBe(
      "Status is any of a, b",
    );
    // Value-less operators must not render a trailing "undefined".
    expect(describeFilter("email", { op: "is_empty", value: null })).toBe(
      "Email is empty",
    );
  });
});

describe("columns", () => {
  it("clamps a resize to sane bounds", () => {
    let state = gridReducer(state0(), { type: "resizeColumn", key: "company", width: 5 });
    expect(columnWidth(state, "company")).toBe(MIN_COLUMN_WIDTH);
    state = gridReducer(state, { type: "resizeColumn", key: "company", width: 99999 });
    expect(columnWidth(state, "company")).toBe(MAX_COLUMN_WIDTH);
  });

  it("reorders columns", () => {
    const state = gridReducer(state0(), { type: "moveColumn", key: "status", toIndex: 0 });
    expect(state.columns[0].key).toBe("status");
    expect(state.columns).toHaveLength(GRID_COLUMNS.length);
  });

  it("refuses to hide the last visible column", () => {
    // A grid with no columns is a blank rectangle with no way back.
    let state = state0();
    for (const column of GRID_COLUMNS.slice(0, -1)) {
      state = gridReducer(state, { type: "toggleColumn", key: column.key });
    }
    expect(visibleColumns(state)).toHaveLength(1);

    const last = GRID_COLUMNS[GRID_COLUMNS.length - 1].key;
    const after = gridReducer(state, { type: "toggleColumn", key: last });
    expect(visibleColumns(after)).toHaveLength(1);
  });

  it("keeps stored order and widths when merging a saved layout", () => {
    const stored = [
      { key: "status", width: 300, visible: true },
      { key: "company", width: 120, visible: false },
    ];
    const merged = mergeColumns(stored);
    expect(merged[0]).toEqual({ key: "status", width: 300, visible: true });
    expect(merged[1]).toEqual({ key: "company", width: 120, visible: false });
    // Everything else is appended, visible, at its default width.
    expect(merged).toHaveLength(GRID_COLUMNS.length);
  });

  it("drops a stored column that no longer exists", () => {
    const merged = mergeColumns([
      { key: "column_removed_in_a_later_release", width: 200, visible: true },
    ]);
    expect(merged.map((c) => c.key)).not.toContain(
      "column_removed_in_a_later_release",
    );
    expect(merged).toHaveLength(GRID_COLUMNS.length);
  });

  it("shows a column added after the view was saved", () => {
    // Otherwise a view saved last year hides every column shipped since,
    // permanently and invisibly.
    const merged = mergeColumns([{ key: "status", width: 150, visible: true }]);
    expect(merged.map((c) => c.key).sort()).toEqual(
      GRID_COLUMNS.map((c) => c.key).sort(),
    );
  });
});

describe("selection", () => {
  it("selects and deselects individual rows", () => {
    let state = gridReducer(state0(), { type: "selectRow", id: "a", selected: true });
    state = gridReducer(state, { type: "selectRow", id: "b", selected: true });
    expect(state.selected.size).toBe(2);
    state = gridReducer(state, { type: "selectRow", id: "a", selected: false });
    expect(Array.from(state.selected)).toEqual(["b"]);
  });

  it("selectAll toggles — a second click clears the page", () => {
    const ids = ["a", "b", "c"];
    let state = gridReducer(state0(), { type: "selectAll", ids });
    expect(state.selected.size).toBe(3);
    state = gridReducer(state, { type: "selectAll", ids });
    expect(state.selected.size).toBe(0);
  });

  it("selectAll on a partially selected page selects the rest", () => {
    let state = gridReducer(state0(), { type: "selectRow", id: "a", selected: true });
    state = gridReducer(state, { type: "selectAll", ids: ["a", "b", "c"] });
    expect(state.selected.size).toBe(3);
  });

  it("keeps selections made on other pages", () => {
    // Selecting across pages then acting once is the whole point of bulk.
    let state = gridReducer(state0(), { type: "selectAll", ids: ["p1a", "p1b"] });
    state = gridReducer(state, { type: "setOffset", offset: 100 });
    state = gridReducer(state, { type: "selectAll", ids: ["p2a"] });
    expect(state.selected.size).toBe(3);
  });
});

describe("saved views", () => {
  const view: CrmSavedView = {
    id: "v1",
    name: "Hot leads",
    view_type: "grid",
    filters_json: { status: { op: "in", value: ["verified"] } },
    sort_json: [{ key: "company", dir: "desc" }],
    columns_json: [{ key: "company", width: 320, visible: true }],
    is_default: false,
    created_at: null,
  };

  it("loading a view restores filters, sort and layout", () => {
    const state = gridReducer(state0(), { type: "loadView", view });
    expect(state.filters).toEqual(view.filters_json);
    expect(state.sort).toEqual(view.sort_json);
    expect(columnWidth(state, "company")).toBe(320);
    expect(state.viewId).toBe("v1");
    expect(state.dirty).toBe(false);
  });

  it("marks the state dirty once the loaded view is changed", () => {
    let state = gridReducer(state0(), { type: "loadView", view });
    state = gridReducer(state, { type: "toggleSort", key: "email", additive: false });
    expect(state.dirty).toBe(true);
  });

  it("does not mark dirty for selection or paging", () => {
    // Those are session state, not part of a view. Ticking a checkbox must
    // not light up "unsaved changes".
    let state = gridReducer(state0(), { type: "loadView", view });
    state = gridReducer(state, { type: "selectRow", id: "a", selected: true });
    state = gridReducer(state, { type: "setOffset", offset: 100 });
    expect(state.dirty).toBe(false);
  });

  it("saving clears the dirty flag", () => {
    let state = gridReducer(state0(), { type: "loadView", view });
    state = gridReducer(state, { type: "toggleSort", key: "email", additive: false });
    state = gridReducer(state, { type: "viewSaved", view: { ...view, name: "Renamed" } });
    expect(state.dirty).toBe(false);
    expect(state.viewName).toBe("Renamed");
  });

  it("persists filters, sort and columns — but not selection or paging", () => {
    let state = gridReducer(state0(), { type: "setSearch", value: "ada" });
    state = gridReducer(state, { type: "selectRow", id: "a", selected: true });
    state = gridReducer(state, { type: "setOffset", offset: 300 });
    const payload = toSavedViewInput(state, "My view", true);

    expect(payload.name).toBe("My view");
    expect(payload.columns_json).toHaveLength(GRID_COLUMNS.length);
    expect(payload).not.toHaveProperty("selected");
    expect(payload).not.toHaveProperty("offset");
    // A saved view is a lens, not a bookmark of what was highlighted.
    expect(payload).not.toHaveProperty("search");
  });

  it("resetView returns to a clean default state", () => {
    let state = gridReducer(state0(), { type: "loadView", view });
    state = gridReducer(state, { type: "resetView" });
    expect(state.viewId).toBeNull();
    expect(state.filters).toEqual({});
    expect(state.columns).toEqual(defaultColumns());
  });
});

describe("CSV export", () => {
  it("quotes fields containing commas, quotes or newlines", () => {
    expect(toCsvValue("plain")).toBe("plain");
    expect(toCsvValue("a,b")).toBe('"a,b"');
    expect(toCsvValue('say "hi"')).toBe('"say ""hi"""');
    expect(toCsvValue("line1\nline2")).toBe('"line1\nline2"');
  });

  it("neutralises formula injection", () => {
    // Excel and Sheets execute a leading =, +, - or @ on open. A company
    // literally named "=SUM(1+1)" must not run when the file is opened, and
    // the export side is the only place that can prevent it.
    expect(toCsvValue("=SUM(1+1)")).toBe("'=SUM(1+1)");
    expect(toCsvValue("+1234")).toBe("'+1234");
    expect(toCsvValue("-cmd")).toBe("'-cmd");
    expect(toCsvValue("@import")).toBe("'@import");
  });

  it("renders null and undefined as empty, not as the words", () => {
    expect(toCsvValue(null)).toBe("");
    expect(toCsvValue(undefined)).toBe("");
  });

  it("writes a header row and flattens tags", () => {
    const row: CrmGridRow = {
      id: "1",
      strategy_id: "s",
      full_name: "Ada Byron",
      title: "Founder",
      company: "Analytical",
      email: "ada@x.test",
      phone: null,
      status: "verified",
      source: "apollo",
      created_at: null,
      updated_at: null,
      tags: [
        { id: "t1", name: "warm", color_token: "primary" },
        { id: "t2", name: "priority", color_token: "accent" },
      ],
      custom: {},
      note_count: 2,
      owner_user_id: null,
      priority: null,
      next_action_at: null,
    };
    const columns = visibleColumns(state0());
    const csv = rowsToCsv([row], columns);
    const [header, body] = csv.split("\r\n");

    expect(header).toContain("Name");
    expect(header).toContain("Company");
    expect(body).toContain("Ada Byron");
    // Tags are objects; they must not serialise as [object Object].
    expect(body).toContain("warm | priority");
    expect(body).not.toContain("[object Object]");
  });
});

describe("keyboard navigation", () => {
  it("moves with the arrow keys and clamps at the edges", () => {
    expect(moveCursor({ row: 0, col: 0 }, "ArrowDown", 5, 3)).toEqual({ row: 1, col: 0 });
    expect(moveCursor({ row: 0, col: 0 }, "ArrowUp", 5, 3)).toEqual({ row: 0, col: 0 });
    expect(moveCursor({ row: 4, col: 2 }, "ArrowRight", 5, 3)).toEqual({ row: 4, col: 2 });
    expect(moveCursor({ row: 0, col: 0 }, "End", 5, 3)).toEqual({ row: 0, col: 2 });
  });

  it("pages by ten rows without overshooting", () => {
    expect(moveCursor({ row: 50, col: 0 }, "PageDown", 55, 3)).toEqual({ row: 54, col: 0 });
    expect(moveCursor({ row: 3, col: 0 }, "PageUp", 55, 3)).toEqual({ row: 0, col: 0 });
  });

  it("tab wraps onto the next row like a spreadsheet", () => {
    expect(tabCursor({ row: 0, col: 2 }, 5, 3, false)).toEqual({ row: 1, col: 0 });
    expect(tabCursor({ row: 1, col: 0 }, 5, 3, true)).toEqual({ row: 0, col: 2 });
  });

  it("tab returns null at the ends so focus can leave the grid", () => {
    // Trapping focus in a grid is a keyboard-only user unable to reach the
    // rest of the page.
    expect(tabCursor({ row: 4, col: 2 }, 5, 3, false)).toBeNull();
    expect(tabCursor({ row: 0, col: 0 }, 5, 3, true)).toBeNull();
  });
});

describe("status editing", () => {
  it("offers only legal transitions, plus the current value", () => {
    // The backend re-validates against the same map; offering a move it will
    // reject is a 422 the user can do nothing about.
    expect(statusOptionsFor("verified")).toEqual(["verified", "flagged", "dropped"]);
    expect(statusOptionsFor("replied")).toEqual(["replied", "meeting_booked"]);
  });

  it("offers nothing but the current value from a terminal stage", () => {
    expect(statusOptionsFor("meeting_booked")).toEqual(["meeting_booked"]);
    expect(statusOptionsFor("dropped")).toEqual(["dropped"]);
  });
});

describe("virtualization window", () => {
  it("renders only the visible slice plus overscan", () => {
    const window = computeWindow(0, 360, { rowCount: 5000, rowHeight: 36, overscan: 8 });
    expect(window.start).toBe(0);
    // 10 visible + 8 overscan; nowhere near 5,000.
    expect(window.end).toBeLessThan(30);
    expect(window.totalHeight).toBe(180_000);
  });

  it("offsets the slice so rows land at the right scroll position", () => {
    const window = computeWindow(3600, 360, { rowCount: 5000, rowHeight: 36, overscan: 8 });
    expect(window.start).toBe(100 - 8);
    expect(window.offsetY).toBe((100 - 8) * 36);
  });

  it("survives an empty list", () => {
    expect(computeWindow(0, 360, { rowCount: 0, rowHeight: 36 })).toEqual({
      start: 0,
      end: 0,
      totalHeight: 0,
      offsetY: 0,
    });
  });

  it("clamps a scroll position past the end of a shrunken list", () => {
    // Applying a filter can leave scrollTop beyond the new end; without the
    // clamp the grid renders an empty window and looks broken.
    const window = computeWindow(180_000, 360, { rowCount: 10, rowHeight: 36 });
    expect(window.start).toBe(0);
    expect(window.end).toBe(10);
  });

  it("clamps a negative scrollTop (iOS overscroll)", () => {
    const window = computeWindow(-200, 360, { rowCount: 100, rowHeight: 36 });
    expect(window.start).toBe(0);
  });
});
