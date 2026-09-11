/** Feature Group 8 — workspaces, members, invitations, approvals, branding. */

import { api } from "./client";
import type { Role } from "../workspace";
import type { PublicBranding } from "../branding";

export interface Membership {
  id: string;
  name: string;
  slug: string;
  role: Role;
  is_personal: boolean;
  brand_name: string | null;
}

export interface CurrentWorkspace {
  id: string;
  name: string;
  slug: string;
  role: Role;
  is_personal: boolean;
  approval_required: boolean;
  branding: PublicBranding;
}

export interface Member {
  user_id: string;
  email: string;
  role: Role;
  joined_at: string | null;
}

export interface Invitation {
  id: string;
  email: string;
  role: Role;
  expires_at: string;
  expired: boolean;
}

export interface PrivateBranding extends PublicBranding {
  subdomain: string | null;
  custom_domain: string | null;
  domain_verified: boolean;
  verification_record: { type: string; name: string; value: string } | null;
  cname_target: string | null;
  approval_required: boolean;
}

export interface Approval {
  sequence_id: string;
  sequence_name: string;
  strategy_id: string;
  campaign: string;
  status: string;
  state: "pending" | "declined";
  requested_by: string | null;
  requested_at: string | null;
  note: string | null;
  lead_statuses: string[];
}

export const listMemberships = (): Promise<Membership[]> => api("/workspaces");
export const getCurrentWorkspace = (): Promise<CurrentWorkspace> => api("/workspaces/current");
export const updateWorkspace = (body: { name?: string; approval_required?: boolean }):
  Promise<CurrentWorkspace> => api("/workspaces/current", { method: "PATCH", body });

export const listMembers = (): Promise<Member[]> => api("/workspaces/current/members");
export const changeRole = (userId: string, role: Role): Promise<Member[]> =>
  api(`/workspaces/current/members/${userId}`, { method: "PATCH", body: { role } });
export const removeMember = (userId: string): Promise<void> =>
  api(`/workspaces/current/members/${userId}`, { method: "DELETE" });

export const listInvitations = (): Promise<Invitation[]> => api("/workspaces/current/invitations");
export const invite = (email: string, role: Role):
  Promise<Invitation & { link: string }> =>
  api("/workspaces/current/invitations", { method: "POST", body: { email, role } });
export const revokeInvitation = (id: string): Promise<void> =>
  api(`/workspaces/current/invitations/${id}`, { method: "DELETE" });
export const acceptInvitation = (token: string):
  Promise<{ workspace_id: string; name: string; role: Role }> =>
  api("/workspaces/invitations/accept", { method: "POST", body: { token } });

export const getBranding = (): Promise<PrivateBranding> => api("/workspaces/current/branding");
export const updateBranding = (body: Partial<{
  white_label_enabled: boolean;
  brand_name: string | null;
  primary_color: string | null;
  support_email: string | null;
  custom_domain: string | null;
}>): Promise<PrivateBranding> => api("/workspaces/current/branding", { method: "PUT", body });
export function uploadLogo(file: File): Promise<PrivateBranding> {
  const formData = new FormData();
  formData.append("file", file);
  return api("/workspaces/current/branding/logo", { method: "POST", formData });
}
export const verifyDomain = (): Promise<PrivateBranding & { verified: boolean }> =>
  api("/workspaces/current/domain/verify", { method: "POST" });

export const listApprovals = (): Promise<Approval[]> => api("/approvals");
export const approveSequence = (id: string): Promise<{ status: string; enrolled: number }> =>
  api(`/sequences/${id}/approve`, { method: "POST" });
export const rejectSequence = (id: string, note: string): Promise<{ status: string }> =>
  api(`/sequences/${id}/reject`, { method: "POST", body: { note } });
