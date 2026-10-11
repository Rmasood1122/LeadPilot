/** Product defect #5: an undeliverable phone verification is shown to admins. */
import { describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api/systemAdmin", () => ({ listConfigWarnings: vi.fn() }));
import { listConfigWarnings } from "@/lib/api/systemAdmin";
import { ConfigWarningsBanner } from "@/components/admin/ConfigWarningsBanner";

function renderBanner() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}><ConfigWarningsBanner /></QueryClientProvider>,
  );
}

describe("ConfigWarningsBanner", () => {
  it("shows each warning the server reports", async () => {
    vi.mocked(listConfigWarnings).mockResolvedValue([{
      key: "phone_verification_undeliverable", severity: "high",
      message: "REQUIRE_PHONE_VERIFICATION is on but SMS_PROVIDER=console cannot deliver",
    }]);
    renderBanner();
    expect(await screen.findByRole("alert")).toHaveTextContent(/SMS_PROVIDER=console/);
  });
  it("renders nothing when the deployment is healthy", async () => {
    vi.mocked(listConfigWarnings).mockResolvedValue([]);
    const { container } = renderBanner();
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
