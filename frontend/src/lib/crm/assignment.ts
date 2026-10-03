/** Lead assignment in the CRM grid (team accounts, Feature 1).
 *
 * Pure functions, so the rules can be unit-tested without rendering a grid.
 * They MIRROR app/services/lead_assignment.py::refusal and exist only to avoid
 * offering a choice the server would refuse -- the server stays the authority,
 * and a stale role here produces a rejected edit with a toast, never a write.
 *
 *   owner / manager  any member, or unassigned
 *   sdr              claim an unassigned lead, or release their own
 *   viewer           nothing
 */

import type { Member } from "@/lib/api/workspaces";
import { atLeast, type Role } from "@/lib/workspace";

export interface TeamContext {
  members: Member[];
  /** The person signed in — NOT the workspace owner the API acts as. */
  meId: string | null;
  role: Role | undefined;
}

export interface OwnerChoice {
  /** null = unassigned */
  value: string | null;
  label: string;
}

const UNASSIGNED: OwnerChoice = { value: null, label: "Unassigned" };

export function ownerLabel(ownerId: string | null, team: TeamContext): string {
  if (!ownerId) return "—";
  if (team.meId && ownerId === team.meId) return "You";
  const member = team.members.find((m) => m.user_id === ownerId);
  // Removed from the workspace after being assigned: say so rather than
  // showing a raw uuid or pretending the lead is unassigned.
  return member ? member.email : "Former member";
}

/** What the owner cell may be changed to, given who holds the lead now.
 *  An empty list means the cell is read-only for this person. */
export function ownerChoices(team: TeamContext, current: string | null): OwnerChoice[] {
  const { role, meId, members } = team;
  if (atLeast(role, "manager")) {
    return [
      UNASSIGNED,
      ...members.map((m) => ({
        value: m.user_id,
        label: m.user_id === meId ? `You (${m.email})` : m.email,
      })),
    ];
  }
  if (role === "sdr" && meId) {
    if (current === null) return [UNASSIGNED, { value: meId, label: "You" }];
    if (current === meId) return [{ value: meId, label: "You" }, UNASSIGNED];
  }
  return [];
}

/** Choices for the bulk bar. For an SDR the server skips, per row, any lead a
 *  colleague already holds — the result toast reports how many. */
export function bulkOwnerChoices(team: TeamContext): OwnerChoice[] {
  if (atLeast(team.role, "manager")) return ownerChoices(team, null);
  if (team.role === "sdr" && team.meId) {
    return [{ value: team.meId, label: "Me" }, UNASSIGNED];
  }
  return [];
}

/** Round-robin hands leads to OTHER people, so it is a manager action. */
export function canDistribute(role: Role | undefined): boolean {
  return atLeast(role, "manager");
}
