import { apiClient } from "./client";

export interface OnboardingStep {
  step: string;
  description: string;
  completed: boolean;
  is_next: boolean;
  action: { label: string; href: string } | null;
}

export interface OnboardingState {
  all_complete: boolean;
  completed_count: number;
  total_steps: number;
  next_step: string | null;
  steps: OnboardingStep[];
  completed_at: string | null;
}

export const onboardingApi = {
  getState: (): Promise<OnboardingState> =>
    apiClient.get("/onboarding/state").then((r: any) => r.data),

  completeStep: (step: string): Promise<{ status: string; step: string }> =>
    apiClient.post("/onboarding/complete-step", { step }).then((r: any) => r.data),
};
