import { api } from "./client";

export interface Me {
  id: string;
  email: string;
  full_name: string | null;
  plan: string;
}

export const getMe = () => api<Me>("/auth/me");
export const saveName = (fullName: string) =>
  api<Me>("/auth/me", { method: "PATCH", body: { full_name: fullName } });
export const changePassword = (currentPassword: string, newPassword: string) =>
  api<{ status: string; signed_out_everywhere: boolean }>("/auth/change-password", {
    body: { current_password: currentPassword, new_password: newPassword },
  });

/** GDPR: everything this account owns, as one JSON document. The password is
 *  re-checked server-side; the workspace header is ignored (/me is personal). */
export const exportMyData = (password: string) =>
  api<Record<string, unknown>>("/me/data-export", { method: "POST", body: { password } });
