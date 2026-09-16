import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock("@/lib/api/strategies", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api/strategies")>();
  return { ...actual, deleteStrategy: vi.fn() };
});

import { toast } from "sonner";
import { ApiError } from "@/lib/api/client";
import { deleteStrategy } from "@/lib/api/strategies";
import { DeleteStrategyDialog } from "@/components/strategy/DeleteStrategyDialog";

beforeAll(() => {
  // jsdom does not implement the modal half of <dialog>.
  HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
    this.removeAttribute("open");
  };
});

const mockedDelete = vi.mocked(deleteStrategy);

function renderDialog() {
  const onDeleted = vi.fn();
  const onClose = vi.fn();
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DeleteStrategyDialog strategyId="s-1" open onClose={onClose} onDeleted={onDeleted} />
    </QueryClientProvider>,
  );
  return { onDeleted, onClose };
}

const passwordField = () => screen.getByLabelText(/enter your password to confirm/i);
const deleteButton = () => screen.getByRole("button", { name: /delete permanently|deleting/i });

describe("DeleteStrategyDialog", () => {
  beforeEach(() => {
    mockedDelete.mockReset();
    vi.mocked(toast.success).mockReset();
  });

  it("cannot be submitted without a password", () => {
    renderDialog();
    expect(deleteButton()).toBeDisabled();
  });

  it("deletes with the entered password, confirms, and hands back", async () => {
    mockedDelete.mockResolvedValue({ deleted: true, id: "s-1", deleted_at: "2026-09-15T00:00:00Z" });
    const { onDeleted } = renderDialog();

    await userEvent.type(passwordField(), "CorrectHorse!1");
    await userEvent.click(deleteButton());

    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(mockedDelete).toHaveBeenCalledWith("s-1", "CorrectHorse!1");
    expect(toast.success).toHaveBeenCalledWith("Strategy deleted.");
  });

  it("shows an error for a wrong password and does not report a deletion", async () => {
    mockedDelete.mockRejectedValue(new ApiError(403, "INVALID_PASSWORD"));
    const { onDeleted } = renderDialog();

    await userEvent.type(passwordField(), "wrong-password");
    await userEvent.click(deleteButton());

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "That password is incorrect. Nothing was deleted.",
    );
    expect(onDeleted).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
    expect(passwordField()).toHaveValue("");
  });

  it("explains a rate limit", async () => {
    mockedDelete.mockRejectedValue(new ApiError(429, "429 Too Many Requests"));
    renderDialog();
    await userEvent.type(passwordField(), "pw");
    await userEvent.click(deleteButton());
    expect(await screen.findByRole("alert")).toHaveTextContent(/too many attempts/i);
  });

  it("locks the dialog while the delete is in flight", async () => {
    mockedDelete.mockReturnValue(new Promise(() => {}));
    const { onClose } = renderDialog();

    await userEvent.type(passwordField(), "pw");
    await userEvent.click(deleteButton());

    await waitFor(() => expect(deleteButton()).toHaveTextContent("Deleting…"));
    expect(deleteButton()).toBeDisabled();
    const cancel = screen.getByRole("button", { name: "Cancel" });
    expect(cancel).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).not.toHaveBeenCalled();
  });
});
