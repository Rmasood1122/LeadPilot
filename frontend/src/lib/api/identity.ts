import { api } from "./client";
import type { VerificationStatus } from "../identity";

export interface Country {
  code: string;
  name: string;
}

export interface IdentityInput {
  personal_country: string;
  account_type: "individual" | "company";
  company_name?: string | null;
  company_country?: string | null;
}

export interface PhoneSendResult {
  status: "sent";
  phone_number_masked: string;
  expires_at: string;
  resend_available_at: string;
}

export const identityApi = {
  countries: () =>
    api<{ countries: Country[] }>("/onboarding/countries", { auth: false }),

  status: () => api<VerificationStatus>("/onboarding/verification"),

  submitIdentity: (body: IdentityInput) =>
    api<VerificationStatus>("/onboarding/identity", { method: "PUT", body }),

  sendCode: (phone_number: string) =>
    api<PhoneSendResult>("/onboarding/phone/send", { body: { phone_number } }),

  verifyCode: (code: string) =>
    api<VerificationStatus & { status: "verified" }>("/onboarding/phone/verify", {
      body: { code },
    }),
};
