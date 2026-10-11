import { api } from "./client";
import type { ApprovePayload, SendApprovalState } from "../sendApproval";

/** Daily send approval (docs/features/daily-send-approval.md). */

export const getSendApproval = () => api<SendApprovalState>("/send-approval/today");

/** NOTE: `body` is passed as an OBJECT. api() stringifies it itself. */
export const approveSendApproval = (payload: ApprovePayload) =>
  api<SendApprovalState>("/send-approval/approve", { method: "POST", body: payload });

export const declineSendApproval = (note?: string) =>
  api<SendApprovalState>("/send-approval/decline", {
    method: "POST", body: note ? { note } : {},
  });
