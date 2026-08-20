"use client";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import { useAuthStore } from "@/lib/stores/authStore";
import { Badge } from "@/components/ui/badge";
import { CheckCircle2, XCircle } from "lucide-react";

function FeatureRow({ label, allowed }: { label: string; allowed: boolean }) {
  return (
    <div className="flex items-center gap-2 text-sm">
      {allowed ? (
        <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
      ) : (
        <XCircle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
      )}
      <span className={allowed ? "" : "text-muted-foreground"}>{label}</span>
    </div>
  );
}

function LimitRow({ label, value }: { label: string; value: number | string }) {
  const display = value === -1 ? "Unlimited" : value;
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{display}</span>
    </div>
  );
}

export function PlanCard() {
  const { user } = useAuthStore();
  const currentPlan = user?.plan ?? "free";

  const { data: plansData } = useQuery({
    queryKey: ["plans"],
    queryFn: () => apiClient.get("/plans").then((r: any) => r.data),
    staleTime: 10 * 60 * 1000,
  });

  const plans = plansData?.plans ?? {};
  const plan = plans[currentPlan] ?? {};
  const upgradePlan = plan.upgrade_to ? plans[plan.upgrade_to] : null;

  return (
    <div className="rounded-lg border bg-card p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">Current Plan</h3>
          <p className="text-sm text-muted-foreground">What your account includes</p>
        </div>
        <Badge variant="outline" className="capitalize text-base px-3 py-1">
          {plan.display_name ?? currentPlan}
        </Badge>
      </div>

      {Object.keys(plan).length > 0 && (
        <>
          <div className="space-y-1.5">
            <LimitRow label="Strategies" value={plan.max_strategies ?? 0} />
            <LimitRow label="Leads per strategy" value={plan.max_leads_per_strategy ?? 0} />
            <LimitRow label="Sequence steps" value={plan.max_sequence_steps ?? 0} />
            <LimitRow label="Analytics history" value={plan.analytics_history_days === -1 ? "Unlimited" : `${plan.analytics_history_days} days`} />
          </div>

          <div className="space-y-1.5">
            <FeatureRow label="Gmail outreach" allowed={(plan.channels ?? []).includes("gmail")} />
            <FeatureRow label="WhatsApp outreach" allowed={(plan.channels ?? []).includes("whatsapp")} />
            <FeatureRow label="A/B testing" allowed={!!plan.ab_testing} />
            <FeatureRow label="Multi-variate testing" allowed={!!plan.multi_variate} />
            <FeatureRow label="Playbook learning access" allowed={!!plan.playbook_access} />
          </div>
        </>
      )}

      {upgradePlan && (
        <div className="rounded-md bg-muted p-3 text-sm space-y-1">
          <p className="font-medium">Upgrade to {upgradePlan.display_name}</p>
          <p className="text-muted-foreground text-xs">
            Unlock{!plan.multi_variate && upgradePlan.multi_variate ? " multi-variate testing," : ""}
            {!plan.playbook_access && upgradePlan.playbook_access ? " playbook learning," : ""}
            {" "}unlimited{upgradePlan.max_strategies === -1 ? " strategies" : ""} and more.
          </p>
          <a
            href={`mailto:upgrade@clienthunter.io?subject=Upgrade to ${upgradePlan.display_name}&body=Hi, I'd like to upgrade from ${plan.display_name ?? currentPlan} to ${upgradePlan.display_name}.`}
            className="inline-block mt-1 text-primary text-xs underline"
          >
            Contact us to upgrade →
          </a>
        </div>
      )}
    </div>
  );
}
