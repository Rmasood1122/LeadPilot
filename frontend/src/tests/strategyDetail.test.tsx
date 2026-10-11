/**
 * Product defect #1: the strategy detail page read a shape the API never sent.
 * The fixture is the real GET /strategies/{id} response shape; it is pinned to
 * the API by tests/test_strategy_status_fixture.py (same keys and types as a
 * live response, validated against StrategyStatusOut).
 */
import { describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, within } from "@testing-library/react";
import fixture from "./fixtures/strategy-status.json";
import type { StrategyOut, VerificationPass } from "@/lib/api/types";
import { verificationSummary } from "@/lib/strategyDetail";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
  useSearchParams: () => new URLSearchParams("id=" + fixture.id),
}));
vi.mock("@tanstack/react-query", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@tanstack/react-query")>();
  return { ...actual, useQueryClient: () => ({ removeQueries: vi.fn() }) };
});
vi.mock("@/lib/api/hooks", () => ({
  useStrategy: () => ({ data: fixture, isLoading: false, error: null }),
}));
vi.mock("@/components/strategy/DeleteStrategyDialog", () => ({ DeleteStrategyDialog: () => null }));
vi.mock("@/components/strategy/ResumeStrategyButton", () => ({ ResumeStrategyButton: () => null }));
vi.mock("@/components/strategy/ReverifyStrategyButton", () => ({ ReverifyStrategyButton: () => null }));
vi.mock("@/components/strategy/OverridePassesPanel", () => ({ OverridePassesPanel: () => null }));
vi.mock("@/components/strategy/OutreachPanel", () => ({ OutreachPanel: () => null }));
vi.mock("@/components/strategy/PipelineHealthCard", () => ({ PipelineHealthCard: () => null }));

import StrategyDetailPage from "@/app/(app)/strategies/detail/page";

const log = fixture.verification as unknown as VerificationPass[];

describe("verificationSummary", () => {
  it("collapses the attempt log to one row per check with its attempt count", () => {
    const rows = verificationSummary(log);
    expect(rows.map((r) => [r.pass_no, r.result, r.attempts])).toEqual([
      [1, "PASS", 1], [2, "PASS", 2], [3, "FAIL", 2],
    ]);
  });
  it("shows the fix that was applied, or why the check still fails", () => {
    const rows = verificationSummary(log);
    expect(rows[0].note).toBeNull();
    expect(rows[1].note).toEqual({ kind: "fix", text: "Market size cites no source" });
    expect(rows[2].note).toEqual({ kind: "failure", text: "Competitor pricing still unsourced" });
  });
  it("starts the count again for a new run of the same check", () => {
    const rerun = [...log, { ...log[0], pass_no: 3, attempt: 1, result: "PASS",
                             fix_description: null, fix_applied: false } as VerificationPass];
    const three = verificationSummary(rerun).find((r) => r.pass_no === 3)!;
    expect([three.result, three.attempts, three.note]).toEqual(["PASS", 1, null]);
  });
  it("a manual sign-off shows who passed it and why", () => {
    const signed = [...log, { pass_no: 3, key: "k", name: "Competitors", attempt: 3,
      result: "PASS", manual_override: true, overridden_by_email: "a@b.co",
      reason: "Checked prices on vendor sites", fix_description: null } as VerificationPass];
    const three = verificationSummary(signed).find((r) => r.pass_no === 3)!;
    expect(three.manual).toBe(true);
    expect(three.note).toEqual({ kind: "manual", text: "a@b.co: Checked prices on vendor sites" });
  });
});

describe("StrategyDetailPage against the real API shape", () => {
  it("renders one card per pipeline with named phases and real counts", () => {
    render(<StrategyDetailPage />);
    const progress = screen.getByRole("region", { name: /pipeline progress/i });
    expect(within(progress).queryByText(/phase pending/i)).toBeNull();
    expect(within(progress).getByText(/strategy pipeline/i)).toBeInTheDocument();
    expect(within(progress).getByText(/gtm pipeline/i)).toBeInTheDocument();
    const p1 = fixture.progress[0].phases[0];
    expect(within(progress).getByText(new RegExp(`1\\. ${p1.title.slice(0, 20)}`)))
      .toBeInTheDocument();
    expect(within(progress).getByText("5/72 steps")).toBeInTheDocument();
    expect(within(progress).getAllByText("5/9").length).toBe(1);
    expect(within(progress).queryByText(/step outputs appear here/i)).toBeNull();
  });

  it("shows each check once, with its attempt count and fix text", () => {
    render(<StrategyDetailPage />);
    const loop = screen.getByRole("region", { name: /verification loop/i });
    const items = within(loop).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(within(loop).getByText(/PASS x2/)).toBeInTheDocument();
    expect(within(loop).getByText(/FAIL x2/)).toBeInTheDocument();
    expect(within(loop).getByText(/fix applied: Market size cites no source/)).toBeInTheDocument();
    expect(within(loop).getByText(/why it failed: Competitor pricing still unsourced/))
      .toBeInTheDocument();
  });

  it("type-checks the fixture as the page's data type", () => {
    const typed: StrategyOut = fixture as unknown as StrategyOut;
    expect(typed.progress[0].phases[0].title).toBeTruthy();
  });
});
