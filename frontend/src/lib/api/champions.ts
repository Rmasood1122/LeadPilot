import { api } from "./client";
import type { ChampionMove, HeldMessage, RoleCheck } from "../champion-tracker";

/** F10 — Champion Tracker: role checks, recorded job changes, held messages. */

export const getRoleCheck = (leadId: string) =>
  api<RoleCheck>(`/leads/${leadId}/role-check`);

/** Re-verify the role now. May spend one paid lead-source lookup. */
export const refreshRoleCheck = (leadId: string) =>
  api<RoleCheck>(`/leads/${leadId}/role-check/refresh`, { method: "POST", body: {} });

/** A person confirms the prospect still holds the role. `body` is an OBJECT —
 *  api() stringifies it itself. */
export const confirmRole = (leadId: string, reason: string, adoptTitle = false) =>
  api<RoleCheck>(`/leads/${leadId}/role-check/confirm`,
                 { method: "POST", body: { reason, adopt_title: adoptTitle } });

export const listChampionMoves = (limit = 50, offset = 0) =>
  api<{ total: number; limit: number; offset: number; items: ChampionMove[] }>(
    `/champions/moves?limit=${limit}&offset=${offset}`);

export const dismissChampionMove = (moveId: string, reason: string) =>
  api<ChampionMove>(`/champions/moves/${moveId}/dismiss`, { method: "POST", body: { reason } });

export const listHeldMessages = (limit = 100) =>
  api<{ total: number; items: HeldMessage[] }>(`/champions/held?limit=${limit}`);
