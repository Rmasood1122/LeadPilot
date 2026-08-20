/**
 * Intake wizard state machine tests (Chunk 7) — pure function tests;
 * no rendering required. Asserts the YES/NO branch, the guard that
 * prevents advancing with empty fields, and round-trip back-navigation.
 */

import { describe, it, expect } from "vitest";
import {
  canAdvance,
  INITIAL_INTAKE,
  nextStep,
  prevStep,
  type IntakeState,
} from "@/components/intake/wizard";

const FILLED_PRODUCT: IntakeState = {
  ...INITIAL_INTAKE,
  product: {
    name: "HVAC inspection service",
    description: "Same-day commercial HVAC inspection and compliance reports.",
    type: "skill",
  },
};

describe("intake wizard — initial state", () => {
  it("starts on the product step", () =>
    expect(INITIAL_INTAKE.step).toBe("product"));

  it("cannot advance with empty product", () =>
    expect(canAdvance(INITIAL_INTAKE)).toBe(false));

  it("can advance once name + description are filled", () =>
    expect(canAdvance(FILLED_PRODUCT)).toBe(true));
});

describe("intake wizard — YES branch (past clients)", () => {
  const atQuestion: IntakeState = {
    ...FILLED_PRODUCT,
    step: "past-clients-question",
    hasPastClients: null,
  };

  it("cannot advance until answered", () =>
    expect(canAdvance(atQuestion)).toBe(false));

  it("YES routes to past-clients step and seeds one empty entry", () => {
    const chose = { ...atQuestion, hasPastClients: true };
    expect(canAdvance(chose)).toBe(true);
    const next = nextStep(chose);
    expect(next.step).toBe("past-clients");
    expect(next.clients).toHaveLength(1);
  });

  it("past-clients step requires at least one filled entry", () => {
    const empty: IntakeState = {
      ...atQuestion,
      step: "past-clients",
      hasPastClients: true,
      clients: [{ details: "", acquisition_story: "" }],
    };
    expect(canAdvance(empty)).toBe(false);
  });

  it("advances to review once all clients are filled", () => {
    const filled: IntakeState = {
      ...atQuestion,
      step: "past-clients",
      hasPastClients: true,
      clients: [
        {
          details: "Fire-protection company, 11-50 staff",
          acquisition_story: "Referral from a mutual contact",
        },
      ],
    };
    expect(canAdvance(filled)).toBe(true);
    expect(nextStep(filled).step).toBe("review");
  });
});

describe("intake wizard — NO branch (no past clients)", () => {
  const chose: IntakeState = {
    ...FILLED_PRODUCT,
    step: "past-clients-question",
    hasPastClients: false,
  };

  it("NO skips past-clients step and goes straight to review", () => {
    const next = nextStep(chose);
    expect(next.step).toBe("review");
    expect(next.clients).toHaveLength(0);
  });
});

describe("intake wizard — back navigation", () => {
  it("review → past-clients when hasPastClients is true", () => {
    const review: IntakeState = {
      ...FILLED_PRODUCT,
      step: "review",
      hasPastClients: true,
      clients: [{ details: "d", acquisition_story: "s" }],
    };
    expect(prevStep(review).step).toBe("past-clients");
  });

  it("review → past-clients-question when hasPastClients is false", () => {
    const review: IntakeState = {
      ...FILLED_PRODUCT,
      step: "review",
      hasPastClients: false,
      clients: [],
    };
    expect(prevStep(review).step).toBe("past-clients-question");
  });

  it("past-clients-question → product", () => {
    const atQ: IntakeState = { ...FILLED_PRODUCT, step: "past-clients-question" };
    expect(prevStep(atQ).step).toBe("product");
  });
});
