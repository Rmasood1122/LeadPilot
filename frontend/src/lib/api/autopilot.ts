import { api } from "./client";
import type {
  AutopilotOptIn, AutopilotView, Diagnostics, LawfulBasis, SendTimeView,
} from "../autopilot";

/** Autopilot launch, best time to send, send diagnostics
 *  (docs/features/autopilot-launch.md). `body` is passed as an OBJECT:
 *  api() stringifies it itself. */

export const getLawfulBasis = () => api<LawfulBasis>("/autopilot/lawful-basis");

export const getAutopilot = (strategyId: string) =>
  api<AutopilotView>(`/strategies/${strategyId}/autopilot`);

export const setAutopilot = (strategyId: string, body: AutopilotOptIn) =>
  api<AutopilotView>(`/strategies/${strategyId}/autopilot`, { method: "PUT", body });

export const getBestTime = (strategyId: string) =>
  api<SendTimeView>(`/strategies/${strategyId}/best-time`);

export const setBestTime = (
  strategyId: string,
  window: { days: number[]; start: string; end: string } | null,
) =>
  // 202 when a window is set: `rescheduling` messages are re-placed in the
  // background. 200 with 0 when cleared.
  api<SendTimeView & { rescheduling: number }>(`/strategies/${strategyId}/best-time`, {
    method: "PUT",
    body: window === null ? { clear: true } : window,
  });

export const setAutopilotTemplate = (strategyId: string, templateId: string | null) =>
  api<AutopilotView>(`/strategies/${strategyId}/autopilot/whatsapp-template`, {
    method: "PUT",
    body: { whatsapp_template_id: templateId },
  });

export const getSendDiagnostics = (strategyId: string) =>
  api<Diagnostics>(`/strategies/${strategyId}/send-diagnostics`);
