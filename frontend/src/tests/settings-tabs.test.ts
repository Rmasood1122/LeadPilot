/**
 * settings-tabs.test.ts — F-SEC-04 frontend follow-up.
 *
 * GET / POST /suppression are admin-only on the server, so the Settings ->
 * Suppression tab is hidden for everyone else instead of rendering a 403.
 */

import { describe, it, expect } from "vitest";

import {
  SETTINGS_TABS,
  resolveSettingsTab,
  visibleSettingsTabs,
} from "@/lib/settings-tabs";

describe("visibleSettingsTabs", () => {
  it("shows every tab, Suppression included, to an admin", () => {
    expect(visibleSettingsTabs(true)).toEqual(SETTINGS_TABS);
    expect(visibleSettingsTabs(true)).toContain("suppression");
  });

  it("hides Suppression from a non-admin", () => {
    expect(visibleSettingsTabs(false)).not.toContain("suppression");
  });

  it("hides Suppression while the session is still loading or unknown", () => {
    expect(visibleSettingsTabs(undefined)).not.toContain("suppression");
    expect(visibleSettingsTabs(null)).not.toContain("suppression");
  });

  it("leaves every other tab, in order, for a non-admin", () => {
    expect(visibleSettingsTabs(false)).toEqual(
      ["appearance", "voice", "integrations", "deliverability", "sharing"],
    );
  });
});

describe("resolveSettingsTab", () => {
  it("keeps the Suppression tab for an admin", () => {
    expect(resolveSettingsTab("suppression", true)).toBe("suppression");
  });

  it("falls back to the default when a non-admin follows ?tab=suppression", () => {
    expect(resolveSettingsTab("suppression", false)).toBe("appearance");
    expect(resolveSettingsTab("suppression", undefined)).toBe("appearance");
  });

  it("does not touch any other selection", () => {
    for (const tab of ["appearance", "voice", "integrations", "deliverability", "sharing"] as const) {
      expect(resolveSettingsTab(tab, false)).toBe(tab);
      expect(resolveSettingsTab(tab, true)).toBe(tab);
    }
  });
});
