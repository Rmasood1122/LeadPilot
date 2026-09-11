/** Feature Group 8: the selected workspace and the role ladder.
 *
 *  The selection lives in localStorage: it is a preference, not a secret --
 *  the server checks membership on every request that carries it. */

export type Role = "owner" | "manager" | "sdr" | "viewer";

const KEY = "leadpilot.workspace";
export const WORKSPACE_HEADER = "X-Workspace-Id";

export function getActiveWorkspace(): string | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function setActiveWorkspace(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(KEY, id);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* private mode / blocked storage: stay in the personal workspace */
  }
}

const RANK: Record<Role, number> = { viewer: 0, sdr: 1, manager: 2, owner: 3 };

export function atLeast(role: Role | undefined, minimum: Role): boolean {
  return role !== undefined && RANK[role] >= RANK[minimum];
}

/** Roles `me` may hand out (mirrors app/services/workspaces.py). */
export function assignableRoles(me: Role | undefined): Role[] {
  if (me === "owner") return ["manager", "sdr", "viewer"];
  if (me === "manager") return ["sdr", "viewer"];
  return [];
}

/** May `me` change or remove someone who currently has `target`? */
export function canManage(me: Role | undefined, target: Role): boolean {
  if (target === "owner") return false;
  return assignableRoles(me).includes(target);
}

export const ROLE_LABELS: Record<Role, string> = {
  owner: "Owner",
  manager: "Manager",
  sdr: "SDR",
  viewer: "Viewer",
};
