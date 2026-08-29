/**
 * Typed frontend API client for admin endpoints.
 * All methods require an admin JWT (enforced server-side).
 */
import { apiClient } from "./client";

export const adminApi = {
  // -------------------------------------------------------------------
  // Users
  // -------------------------------------------------------------------
  listUsers: async (page = 1, pageSize = 50) =>
    apiClient.get(`/admin/users?page=${page}&page_size=${pageSize}`).then((r: any) => r.data),

  getUserDetail: async (userId: string) =>
    apiClient.get(`/admin/users/${userId}`).then((r: any) => r.data),

  suspendUser: async (userId: string, reason: string) =>
    apiClient.post(`/admin/users/${userId}/suspend`, { reason }).then((r: any) => r.data),

  unsuspendUser: async (userId: string) =>
    apiClient.post(`/admin/users/${userId}/unsuspend`).then((r: any) => r.data),

  // -------------------------------------------------------------------
  // Suppression list
  // -------------------------------------------------------------------
  listSuppression: async (page = 1, pageSize = 100) =>
    apiClient
      .get(`/admin/suppression-list?page=${page}&page_size=${pageSize}`)
      .then((r: any) => r.data),

  addSuppression: async (email: string, reason: string) =>
    apiClient.post("/admin/suppression-list", { email, reason }).then((r: any) => r.data),

  removeSuppression: async (email: string) =>
    apiClient.delete(`/admin/suppression-list/${encodeURIComponent(email)}`).then((r: any) => r.data),

  // -------------------------------------------------------------------
  // Task errors
  // -------------------------------------------------------------------
  listTaskErrors: async (unresolvedOnly = true, page = 1, pageSize = 50) =>
    apiClient
      .get(`/admin/task-errors?unresolved_only=${unresolvedOnly}&page=${page}&page_size=${pageSize}`)
      .then((r: any) => r.data),

  resolveTaskError: async (errorId: string, note: string) =>
    apiClient
      .post(`/admin/task-errors/${errorId}/resolve`, { resolution_note: note })
      .then((r: any) => r.data),

  // -------------------------------------------------------------------
  // Circuit breakers
  // -------------------------------------------------------------------
  // ── Feature 2/3 admin surfaces ─────────────────────────────────────────
  // Tutorial completions are AGGREGATE ONLY — the payload deliberately
  // carries no user identifier. Support tickets DO carry the requester's
  // email, because a ticket you cannot reply to is useless.
  getTutorialCompletions: async () =>
    apiClient.get<import("./types").AdminTutorialCompletions>(
      "/admin/tutorials/completions"),

  listSupportTickets: async (status?: string) =>
    apiClient.get<{ open_count: number;
                    tickets: import("./types").AdminSupportTicket[] }>(
      `/admin/support/tickets${status ? `?status=${status}` : ""}`),

  resolveSupportTicket: async (ticketId: string, note: string) =>
    apiClient.post<{ id: string; status: string }>(
      `/admin/support/tickets/${ticketId}/resolve`, { note }),

  listCircuitBreakers: async () =>
    apiClient.get("/admin/circuit-breakers").then((r: any) => r.data),

  resetCircuitBreaker: async (provider: string) =>
    apiClient.post(`/admin/circuit-breakers/${provider}/reset`).then((r: any) => r.data),

  // -------------------------------------------------------------------
  // Playbook
  // -------------------------------------------------------------------
  listPlaybookScores: async (userId?: string, page = 1, pageSize = 100) => {
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (userId) params.set("user_id", userId);
    return apiClient.get(`/admin/playbook/scores?${params}`).then((r: any) => r.data);
  },

  recomputePlaybook: async () =>
    apiClient.post("/admin/playbook/recompute").then((r: any) => r.data),

  // -------------------------------------------------------------------
  // Health
  // -------------------------------------------------------------------
  getSystemHealth: async () =>
    apiClient.get("/health").then((r: any) => r.data),

  getLearningLoopHealth: async () =>
    apiClient.get("/health/learning-loop").then((r: any) => r.data),

  getChannelHealth: async () =>
    apiClient.get("/health/channels").then((r: any) => r.data),

  getCeleryStats: async () =>
    apiClient.get("/admin/celery-stats").then((r: any) => r.data),

  // -------------------------------------------------------------------
  // Encryption key rotation
  // -------------------------------------------------------------------
  rotateEncryptionKey: async () =>
    apiClient.post("/admin/rotate-encryption-key").then((r: any) => r.data),
};
