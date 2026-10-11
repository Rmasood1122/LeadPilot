/**
 * Product defect #4: the "+ New draft" WhatsApp editor always sent
 * variable_descriptions: {}, and the server requires one description per
 * placeholder, so any template with {{1}} -- including the editor's own
 * example -- was refused. #28: the editor now also checks for the STOP
 * opt-out keyword the server requires (a legal guard).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("@/lib/api/campaigns", () => ({
  createTemplate: vi.fn(async (input: unknown) => ({ id: "t1", name: "x", language: "en_US",
                                                      status: "draft", ...(input as object) })),
  updateTemplate: vi.fn(async (id: string, input: unknown) => ({ id, name: "x", language: "en_US",
                                                                 status: "draft", ...(input as object) })),
}));

import { createTemplate, updateTemplate } from "@/lib/api/campaigns";
import { TemplateEditor } from "@/components/campaigns/TemplateEditor";
import {
  hasOptOutInstruction, missingDescriptions, needsOptOutInstruction, placeholderNumbers,
  variableDescriptions,
} from "@/lib/whatsappTemplate";

const EXAMPLE = "Hi {{1}}, Sam from LeadPilot. Reply STOP to opt out.";

describe("template rules", () => {
  it("finds each placeholder once, in order", () => {
    expect(placeholderNumbers("{{2}} {{1}} {{2}}")).toEqual([1, 2]);
    expect(placeholderNumbers("no vars")).toEqual([]);
  });
  it("sends exactly one description per placeholder in the body", () => {
    expect(variableDescriptions(EXAMPLE, { "1": " first name ", "3": "stale" }))
      .toEqual({ "1": "first name" });
    expect(missingDescriptions("{{1}} {{2}}", { "1": "a" })).toEqual([2]);
  });
  it("requires an opt-out instruction on marketing templates, like the server", () => {
    expect(hasOptOutInstruction(EXAMPLE)).toBe(true);
    expect(hasOptOutInstruction("reply STOP to unsubscribe")).toBe(true);
    expect(hasOptOutInstruction("STOP to unsubscribe")).toBe(true);
    expect(hasOptOutInstruction("Text STOP anytime")).toBe(true);
    for (const body of ["don't stop", "Reply NOSTOP", "NON-STOP deals for you",
                        "meet us at the BUS STOP", "see https://x.example/STOP",
                        "Reply to Sam about the price. STOP"]) {
      expect(hasOptOutInstruction(body)).toBe(false);
    }
    expect(needsOptOutInstruction("marketing")).toBe(true);
    expect(needsOptOutInstruction("utility")).toBe(false);
  });
});

describe("TemplateEditor", () => {
  beforeEach(() => {
    vi.mocked(createTemplate).mockClear();
    vi.mocked(updateTemplate).mockClear();
  });

  it("saves its own example with a description for {{1}}", async () => {
    const onSave = vi.fn();
    render(<TemplateEditor onSave={onSave} onClose={() => undefined} />);
    await userEvent.type(screen.getByLabelText(/name/i), "intro offer");
    await userEvent.click(screen.getByLabelText(/^body/i));
    await userEvent.paste(EXAMPLE);
    const save = screen.getByRole("button", { name: /save draft/i });
    expect(save).toBeDisabled(); // {{1}} has no description yet
    await userEvent.type(screen.getByLabelText(/what goes in \{\{1\}\}/i), "first name");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(createTemplate).toHaveBeenCalledWith({
      name: "intro_offer", language: "en_US", category: "marketing",
      body: EXAMPLE, variable_descriptions: { "1": "first name" },
    });
    expect(onSave).toHaveBeenCalled();
  });

  it("will not save a body without the STOP opt-out", async () => {
    render(<TemplateEditor onSave={vi.fn()} onClose={() => undefined} />);
    await userEvent.type(screen.getByLabelText(/name/i), "intro");
    await userEvent.type(screen.getByLabelText(/^body/i), "NON-STOP deals from LeadPilot.");
    expect(screen.getByRole("button", { name: /save draft/i })).toBeDisabled();
    expect(screen.getByText(/must tell the recipient how to opt out/i)).toBeInTheDocument();
  });

  it("does not require it when editing a utility template", async () => {
    render(<TemplateEditor
      initial={{ id: "u1", name: "confirm", language: "en_US", status: "draft",
                 category: "utility", body: "Your meeting is confirmed.",
                 variable_descriptions: {} }}
      onSave={vi.fn()} onClose={() => undefined} />);
    expect(screen.getByRole("button", { name: /save draft/i })).toBeEnabled();
  });

  it("edits keep the saved descriptions and send them with the body", async () => {
    render(<TemplateEditor
      initial={{ id: "t9", name: "intro", language: "en_US", status: "draft",
                 body: EXAMPLE, variable_descriptions: { "1": "first name" } }}
      onSave={vi.fn()} onClose={() => undefined} />);
    expect(screen.getByLabelText(/what goes in \{\{1\}\}/i)).toHaveValue("first name");
    await userEvent.click(screen.getByRole("button", { name: /save draft/i }));
    expect(updateTemplate).toHaveBeenCalledWith("t9", {
      body: EXAMPLE, variable_descriptions: { "1": "first name" },
    });
  });
});
