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
