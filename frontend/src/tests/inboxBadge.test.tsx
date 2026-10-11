/** Product defect #23: GET /inbox/count ("nav badge") had no caller. The
 *  Inbox nav entry now shows how many prospects are waiting on a reply. */
import { describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/lib/api/inbox", () => ({ countInbox: vi.fn() }));
import { countInbox } from "@/lib/api/inbox";
import { InboxBadge, inboxBadgeText } from "@/components/shell/InboxBadge";

function renderBadge() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><InboxBadge /></QueryClientProvider>);
}

describe("inbox badge", () => {
  it("formats the count", () => {
    expect(inboxBadgeText(0)).toBeNull();
    expect(inboxBadgeText(7)).toBe("7");
    expect(inboxBadgeText(120)).toBe("99+");
  });
  it("shows the number waiting, with an accessible label", async () => {
    vi.mocked(countInbox).mockResolvedValue({ needs_reply: 4 });
    renderBadge();
    expect(await screen.findByLabelText("4 waiting on a reply")).toHaveTextContent("4");
  });
  it("shows nothing when nobody is waiting", async () => {
    vi.mocked(countInbox).mockResolvedValue({ needs_reply: 0 });
    const { container } = renderBadge();
    await Promise.resolve();
    expect(container).toBeEmptyDOMElement();
  });
});
