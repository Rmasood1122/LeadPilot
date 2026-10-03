/**
 * Which Settings tabs a user sees.
 *
 * The Suppression tab lists and edits the deployment-wide suppression list.
 * Both of its endpoints (GET / POST /suppression) are admin-only on the
 * server (F-SEC-04), so for anyone else the tab could only ever show a 403.
 * It is hidden for non-admins rather than left to fail.
 *
 * This is presentation only. The server is what enforces access; hiding the
 * tab grants nothing and showing it would grant nothing either.
 */

export type SettingsTab =
  | "appearance"
  | "voice"
  | "integrations"
  | "deliverability"
  | "sharing"
  | "suppression";

export const SETTINGS_TABS: SettingsTab[] = [
  "appearance", "voice", "integrations", "deliverability", "sharing", "suppression",
];

/** Tabs that only an admin may see. */
export const ADMIN_ONLY_TABS: ReadonlySet<SettingsTab> = new Set<SettingsTab>(["suppression"]);

export const DEFAULT_SETTINGS_TAB: SettingsTab = "appearance";

/** The tabs to render, in order. `isAdmin` is `user.is_admin` from useAuthStore;
 *  anything other than `true` (false, undefined, still loading) hides the
 *  admin-only tabs. */
export function visibleSettingsTabs(isAdmin: boolean | undefined | null): SettingsTab[] {
  return SETTINGS_TABS.filter((tab) => isAdmin === true || !ADMIN_ONLY_TABS.has(tab));
}

/** The tab to actually show: the selected one if this user may see it,
 *  otherwise the default. Covers a non-admin following a ?tab=suppression
 *  link, and an admin whose session is still loading. */
export function resolveSettingsTab(
  selected: SettingsTab,
  isAdmin: boolean | undefined | null,
): SettingsTab {
  return visibleSettingsTabs(isAdmin).includes(selected) ? selected : DEFAULT_SETTINGS_TAB;
}
