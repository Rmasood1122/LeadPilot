import { api } from "./client";
import type { PublicDashboard, ShareLink } from "../shareLinks";

export const listShareLinks = () => api<ShareLink[]>("/share-links");

export const createShareLink = (body: { label: string; strategy_id?: string | null;
                                        expires_in_days: number }) =>
  api<ShareLink & { token: string; url: string }>("/share-links", { body });

export const revokeShareLink = (id: string) =>
  api<ShareLink>(`/share-links/${id}`, { method: "DELETE" });

export const getPublicDashboard = (token: string) =>
  api<PublicDashboard>(`/public/roi/${encodeURIComponent(token)}`, { auth: false });
