/** Feature Group 2 — voice profile, per-lead personalization inputs, Loom. */

import { api } from "./client";

export interface StyleProfile {
  tone: string;
  formality: number;
  vocabulary_level: "plain" | "conversational" | "professional" | "technical";
  sentence_length: "short" | "medium" | "long";
  avg_words_per_sentence: number | null;
  humor: "none" | "light" | "frequent";
  greeting_style: string;
  signoff_style: string;
  signature_habits: string[];
  do: string[];
  dont: string[];
  summary: string;
}

export interface StyleProfileState {
  profile: StyleProfile | null;
  samples: string[];
  updated_at: string | null;
}

export function getStyleProfile(): Promise<StyleProfileState> {
  return api("/me/style-profile");
}

export function saveStyleProfile(samples: string[]): Promise<StyleProfileState> {
  return api("/me/style-profile", { method: "PUT", body: { samples } });
}

export function clearStyleProfile(): Promise<void> {
  return api("/me/style-profile", { method: "DELETE" });
}

export interface LinkedInPost {
  text: string;
  posted_at: string | null;
  url: string | null;
}

export interface NewsItem {
  headline: string;
  summary: string;
  url: string | null;
  source: string | null;
  published_at: string;
}

export interface LoomState {
  status?: "suggested" | "recorded" | "skipped";
  title?: string;
  script?: string;
  on_screen?: string;
  share_url?: string;
  embed_id?: string;
  suggested_at?: string;
  recorded_at?: string;
}

export interface LeadPersonalization {
  linkedin_url: string | null;
  /** null = never fetched; [] = fetched, nothing found. */
  linkedin_posts: LinkedInPost[] | null;
  linkedin_posts_fetched_at: string | null;
  company_news: NewsItem[] | null;
  company_news_fetched_at: string | null;
  loom: LoomState;
  loom_page_url: string | null;
}

export function getLeadPersonalization(leadId: string): Promise<LeadPersonalization> {
  return api(`/leads/${leadId}/personalization`);
}

export function refreshLeadPersonalization(leadId: string): Promise<LeadPersonalization> {
  return api(`/leads/${leadId}/personalization/refresh`, { method: "POST" });
}

export function setLeadLinkedInUrl(
  leadId: string,
  linkedinUrl: string | null,
): Promise<LeadPersonalization> {
  return api(`/leads/${leadId}/linkedin-url`, {
    method: "PUT",
    body: { linkedin_url: linkedinUrl },
  });
}

export function writeLoomScript(leadId: string): Promise<LeadPersonalization> {
  return api(`/leads/${leadId}/loom/script`, { method: "POST" });
}

export function recordLoom(leadId: string, shareUrl: string): Promise<LeadPersonalization> {
  return api(`/leads/${leadId}/loom`, { method: "PUT", body: { share_url: shareUrl } });
}

export function skipLoom(leadId: string): Promise<LeadPersonalization> {
  return api(`/leads/${leadId}/loom/skip`, { method: "POST" });
}

export interface PublicVideo {
  first_name: string;
  company: string | null;
  title: string | null;
  embed_url: string;
}

/** No auth: opened by a prospect from an email. */
export function getPublicVideo(token: string): Promise<PublicVideo> {
  return api(`/public/video?t=${encodeURIComponent(token)}`, { auth: false });
}
