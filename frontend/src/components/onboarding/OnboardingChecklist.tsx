"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { CheckCircle2, Circle, ArrowRight, ChevronDown, ChevronUp } from "lucide-react";
import Link from "next/link";

interface Step {
  step: string;
  description: string;
  completed: boolean;
  is_next: boolean;
  action: { label: string; href: string } | null;
}

export function OnboardingChecklist() {
  const [collapsed, setCollapsed] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ["onboarding-state"],
    queryFn: () => apiClient.get("/onboarding/state").then((r: any) => r.data),
    staleTime: 30_000,
  });

  if (isLoading || !data) return null;

  // If all complete and user has dismissed (stored in localStorage-free state: just hide after all done)
  if (data.all_complete && collapsed) return null;

  if (data.all_complete) {
    return (
      <div className="rounded-lg border bg-green-50 border-green-200 p-3 flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm text-green-800">
          <CheckCircle2 className="w-4 h-4" />
          You&apos;re all set — LeadPilot is fully configured.
        </div>
        <Button variant="ghost" size="sm" onClick={() => setCollapsed(true)} className="text-xs">
          Dismiss
        </Button>
      </div>
    );
  }

  const steps: Step[] = data.steps ?? [];

  if (collapsed) {
    const pct = Math.round((data.completed_count / data.total_steps) * 100);
    return (
      <div
        className="rounded-lg border bg-card p-3 cursor-pointer flex items-center gap-3"
        onClick={() => setCollapsed(false)}
      >
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-sm font-medium">Getting started</span>
            <span className="text-xs text-muted-foreground">{data.completed_count}/{data.total_steps}</span>
          </div>
          <div className="h-1.5 rounded-full bg-muted overflow-hidden">
            <div className="h-full bg-primary rounded-full transition-all" style={{ width: `${pct}%` }} />
          </div>
        </div>
        <ChevronDown className="w-4 h-4 text-muted-foreground flex-shrink-0" />
      </div>
    );
  }

  return (
    <div className="rounded-lg border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-sm">Getting started with LeadPilot</h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {data.completed_count} of {data.total_steps} steps complete
          </p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setCollapsed(true)}>
          <ChevronUp className="w-4 h-4" />
        </Button>
      </div>

      <div className="space-y-2">
        {steps.map((step) => (
          <div
            key={step.step}
            className={`flex items-center gap-3 py-1.5 px-2 rounded-md ${
              step.is_next ? "bg-accent/50" : ""
            }`}
          >
            {step.completed ? (
              <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
            ) : step.is_next ? (
              <ArrowRight className="w-4 h-4 text-primary flex-shrink-0" />
            ) : (
              <Circle className="w-4 h-4 text-muted-foreground flex-shrink-0" />
            )}

            <span
              className={`text-sm flex-1 ${
                step.completed
                  ? "text-muted-foreground line-through"
                  : step.is_next
                  ? "font-medium"
                  : "text-muted-foreground"
              }`}
            >
              {step.description}
            </span>

            {step.is_next && step.action && (
              <Link href={step.action.href}>
                <Button size="sm" variant="outline" className="h-6 text-xs px-2">
                  {step.action.label}
                </Button>
              </Link>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
