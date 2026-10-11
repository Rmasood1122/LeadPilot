/** Product defect #23: the Pipeline Health Score endpoint had no UI. */
import { describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api/pipelineHealth", () => ({ getPipelineHealth: vi.fn() }));
import { getPipelineHealth } from "@/lib/api/pipelineHealth";
import { PipelineHealthCard } from "@/components/strategy/PipelineHealthCard";

describe("PipelineHealthCard", () => {
  it("shows the score, band, message and the four parts", async () => {
    vi.mocked(getPipelineHealth).mockResolvedValue({
      score: 46, band: "low", message: "Pipeline thinning. Add 10 leads this week.",
      components: { reply_rate: 4, completion: 50, freshness: 100, conversations: 30 },
      updated_at: "2026-10-11T00:00:00Z",
    });
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={client}><PipelineHealthCard strategyId="s1" /></QueryClientProvider>);
    const card = await screen.findByRole("region", { name: /pipeline health/i });
    expect(card).toHaveTextContent("46/100 low");
    expect(card).toHaveTextContent("Pipeline thinning. Add 10 leads this week.");
    expect(card).toHaveTextContent("Lead freshness: 100");
    expect(getPipelineHealth).toHaveBeenCalledWith("s1");
  });
});
