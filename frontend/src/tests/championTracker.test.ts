import { describe, expect, it } from "vitest";

import {
  MIN_REASON,
  ageText,
  attemptText,
  canAdoptTitle,
  canConfirm,
  canRefresh,
  decisionText,
  moveOutcomeText,
  moveText,
  panelVisible,
  reasonError,
  stateLabel,
  stateTone,
  type ChampionMove,
  type RoleCheck,
} from "@/lib/champion-tracker";

function check(overrides: Partial<RoleCheck> = {}): RoleCheck {
  return {
    lead_id: "l1", enabled: true, title: "VP Sales", company: "Acme",
    state: null, last_outcome: null, observed_title: null, observed_company: null,
    checked_at: null, attempted_at: null, retry_after: null, confirmed_by: null,
    observed_at: "2026-06-01T00:00:00Z", age_days: 120, champion_kind: null,
    previous: null,
    send_decision: { would_send: false, blocked: false, held: true,
                     reason: "role data is 120 days old (limit 90) - re-verification queued",
                     would_hold_if_enabled: "role data is 120 days old (limit 90)" },
    held_messages: [], move: null, attempts: [],
    settings: { enabled: true, staleness_days: 90, run_cap: 100, account_monthly_units: 200 },
    ...overrides,
  };
}

function move(overrides: Partial<ChampionMove> = {}): ChampionMove {
  return {
    id: "m1", old_lead_id: "l1", new_lead_id: "l2",
    new_lead: { id: "l2", full_name: "Sara Khan", title: "Head of Sales", company: "NewCo",
                email: "sara@newco.com", status: "verified" },
    champion_kind: "positive_reply", from_company: "Acme", from_title: "VP Sales",
    to_company: "NewCo", to_title: "Head of Sales", to_domain: "newco.com",
    trigger: "refresh", outcome: "lead_created", detail: null,
    detected_at: "2026-10-01T00:00:00Z", dismissed_at: null, dismiss_reason: null,
    ...overrides,
  };
}

describe("decisionText", () => {
  it("says why a message is held", () => {
    expect(decisionText(check())).toBe(
      "Messages are held: role data is 120 days old (limit 90) - re-verification queued.");
  });

  it("says a departure blocks, whatever the flag", () => {
    const blocked = check({ enabled: false, move: move(),
      send_decision: { would_send: false, blocked: true, held: false,
                       reason: "left Acme - the old address is closed" } });
    expect(decisionText(blocked)).toBe(
      "Messages are blocked: left Acme - the old address is closed.");
  });

  it("is honest when the feature is off", () => {
    expect(decisionText(check({ enabled: false,
      send_decision: { would_send: true, blocked: false, held: false, reason: null,
                       would_hold_if_enabled: "role data is 120 days old" } })))
      .toContain("If it were on, messages would be held");
    expect(decisionText(check({ enabled: false,
      send_decision: { would_send: true, blocked: false, held: false, reason: null,
                       would_hold_if_enabled: null } })))
      .toContain("fresh enough");
  });

  it("says fresh roles send", () => {
    expect(decisionText(check({ send_decision: { would_send: true, blocked: false,
                                                 held: false, reason: null } })))
      .toBe("Messages will send: the role is fresh.");
  });
});

describe("state", () => {
  it("labels and tones each state, departure first", () => {
    expect(stateLabel(check())).toBe("Not checked yet");
    expect(stateLabel(check({ state: "title_changed" }))).toBe("Title changed");
    expect(stateTone(check({ state: "title_changed" }))).toBe("warning");
    expect(stateTone(check({ state: "confirmed" }))).toBe("success");
    expect(stateLabel(check({ state: "current", move: move() }))).toBe("Left the company");
    expect(stateTone(check({ move: move() }))).toBe("destructive");
    expect(stateLabel(check({ state: "confirmed",
                              move: move({ dismissed_at: "2026-10-02T00:00:00Z" }) })))
      .toBe("Role confirmed by a person");
  });
});

describe("actions", () => {
  it("offers re-verify only while on and nobody has left", () => {
    expect(canRefresh(check())).toBe(true);
    expect(canRefresh(check({ enabled: false }))).toBe(false);
    expect(canRefresh(check({ move: move() }))).toBe(false);
    expect(canRefresh(check({ move: move({ dismissed_at: "2026-10-02T00:00:00Z" }) })))
      .toBe(true);
  });

  it("offers confirm for a held prospect, never for a departed one", () => {
    expect(canConfirm(check())).toBe(true);
    expect(canConfirm(check({ move: move() }))).toBe(false);
    expect(canConfirm(check({ send_decision: { would_send: true, blocked: false,
                                               held: false, reason: null } })))
      .toBe(false);
    expect(canConfirm(check({ state: "title_changed",
      send_decision: { would_send: true, blocked: false, held: false, reason: null } })))
      .toBe(true);
  });

  it("offers the newer title only when it differs", () => {
    expect(canAdoptTitle(check({ observed_title: "CRO" }))).toBe(true);
    expect(canAdoptTitle(check({ observed_title: "VP Sales" }))).toBe(false);
    expect(canAdoptTitle(check())).toBe(false);
  });

  it("requires a real reason", () => {
    expect(reasonError("ok")).toBe(`Say why in at least ${MIN_REASON} characters.`);
    expect(reasonError("   spoke today ")).toBeNull();
  });
});

describe("panelVisible", () => {
  it("hides when off and nothing was recorded", () => {
    expect(panelVisible(check({ enabled: false }))).toBe(false);
    expect(panelVisible(undefined)).toBe(false);
  });

  it("shows when off but a departure or a hold exists", () => {
    expect(panelVisible(check({ enabled: false, move: move() }))).toBe(true);
    expect(panelVisible(check({ enabled: false, held_messages: [{
      id: "x", lead_id: "l1", channel: "email", step_no: 1, status: "failed",
      reason: "r", scheduled_at: null }] }))).toBe(true);
  });
});

describe("text", () => {
  it("describes a move and what was done", () => {
    expect(moveText(move())).toBe("Moved from VP Sales at Acme to Head of Sales at NewCo.");
    expect(moveText(move({ from_title: null, from_company: null, to_title: null })))
      .toBe("Moved from their old role to NewCo.");
    expect(moveOutcomeText(move())).toContain("re-engagement lead was created");
    expect(moveOutcomeText(move({ outcome: "suppressed" }))).toContain("opted out");
    expect(moveOutcomeText(move({ outcome: "something_new" }))).toBe("something_new");
  });

  it("shows age against the limit", () => {
    expect(ageText(check())).toBe("role observed 120 days ago (limit 90)");
    expect(ageText(check({ age_days: 0 }))).toBe("role observed today");
    expect(ageText(check({ age_days: 1 }))).toBe("role observed 1 day ago (limit 90)");
    expect(ageText(check({ age_days: null }))).toBe("");
  });

  it("prices lookups honestly", () => {
    expect(attemptText({ id: "a", step: "champion_role", provider: "apollo",
                         operation: "role_check", outcome: "title_changed", cached: false,
                         cost_units: 1, created_at: null }))
      .toBe("apollo role check: title changed (1 unit)");
    expect(attemptText({ id: "b", step: "champion_apollo", provider: "hunter",
                         operation: "verify", outcome: "valid", cached: true,
                         cost_units: 0, created_at: null }))
      .toBe("hunter verify: valid (cache hit, no charge)");
  });
});
