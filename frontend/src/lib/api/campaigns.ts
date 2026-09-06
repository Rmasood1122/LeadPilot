import { api } from "./client";
import type { CampaignOverview, SequenceOut, TemplateOut } from "./types";

export function getCampaign(strategyId: string): Promise<CampaignOverview> {
  return api(`/strategies/${strategyId}/campaign`);
}

export function pauseCampaign(strategyId: string) {
  return api(`/strategies/${strategyId}/campaign/pause`, { method: "POST" });
}

export function resumeCampaign(strategyId: string) {
  return api(`/strategies/${strategyId}/campaign/resume`, { method: "POST" });
}

export function listSequences(strategyId: string): Promise<SequenceOut[]> {
  return api(`/strategies/${strategyId}/sequences`);
}

export function listTemplates(): Promise<{ templates: TemplateOut[] }> {
  return api("/whatsapp/templates");
}

export function createTemplate(input: {
  name: string;
  language: string;
  category: string;
  body: string;
  variable_descriptions: Record<string, string>;
}): Promise<TemplateOut> {
  return api("/whatsapp/templates", { body: input });
}

export function updateTemplate(
  id: string,
  input: Partial<{ body: string; category: string; variable_descriptions: Record<string, string> }>,
): Promise<TemplateOut> {
  return api(`/whatsapp/templates/${id}`, { method: "PUT", body: input });
}

export function submitTemplate(id: string): Promise<TemplateOut> {
  return api(`/whatsapp/templates/${id}/submit`, { method: "POST" });
}

export function syncTemplate(id: string): Promise<TemplateOut> {
  return api(`/whatsapp/templates/${id}/sync`, { method: "POST" });
}

export function generateTemplates(
  strategyId: string,
): Promise<{ templates: TemplateOut[]; note: string }> {
  return api("/whatsapp/templates/generate", {
    body: { strategy_id: strategyId },
  });
}

/** Engagement Hub, Feature 1 — per-step automatic follow-up.
 *
 *  Both fields are optional so the toggle and the delay input are independent
 *  controls: flipping the switch must not also re-send (and possibly clobber)
 *  a delay the user is halfway through typing.
 *
 *  POST, not PATCH — the path the backend exposes. It is idempotent either
 *  way; it writes exactly the fields it is sent. */
export function updateFollowupSettings(
  sequenceId: string,
  stepNo: number,
  settings: { enabled?: boolean; delay_hours?: number },
): Promise<{
  sequence_id: string;
  step_no: number;
  followup_enabled: boolean;
  followup_delay_hours: number;
}> {
  return api(`/sequences/${sequenceId}/steps/${stepNo}/followup-settings`, {
    method: "POST",
    body: settings,
  });
}
