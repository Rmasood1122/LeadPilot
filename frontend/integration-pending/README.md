# integration-pending/(dashboard)

These four pages came from the m8-final frontend delivery but were written
against a dashboard layout that does not exist in the real M5 frontend:

- they import 11 components that were never delivered in any milestone zip
  (MeetingRateChart, ReplyRateChart, OutcomesFunnel, QuickStats, ThemeSection,
  AccountSection, IntegrationsSection, KanbanPipeline, CampaignSummaryRow,
  CampaignSequenceView, LeadStatusBoard);
- `(dashboard)/page.tsx` resolves to `/`, which conflicts with the real M5
  root `src/app/page.tsx` (session redirect to /pipeline or /login).

They are parked here (outside src/, so Next.js ignores them) instead of
deleted, as reference for wiring their delivered M8 companions —
SendTimeCard, SubjectLineCard, MultiVariateResults, PersonalizationHealth
and PlanCard DO exist under src/components/ and resolve. (OnboardingChecklist
was deleted on 2026-10-11: never mounted, and nothing marks onboarding steps
complete -- docs/program/fixes/product-defects.md #22.)

The live M5 route groups `(app)` + `(auth)` remain the real UI.
