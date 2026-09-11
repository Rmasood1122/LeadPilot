import { cn } from "@/lib/utils";

const tones: Record<string, string> = {
  default: "bg-muted text-muted-foreground",
  primary: "bg-primary text-primary-foreground",
  success: "bg-success text-white",
  warning: "bg-warning text-white",
  destructive: "bg-destructive text-white",
  accent: "bg-accent text-accent-foreground",
};

// Combined-build: the M8 admin pages use the shadcn `variant` API; the M5
// theme engine uses `tone`. Accept both — `variant` maps onto tones.
const variantToTone: Record<string, keyof typeof tones> = {
  default: "primary",
  secondary: "default",
  outline: "default",
  destructive: "destructive",
  success: "success",
  warning: "warning",
};

export function Badge({
  tone,
  variant,
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & {
  tone?: keyof typeof tones;
  variant?: string;
}) {
  const resolved = tone ?? (variant ? variantToTone[variant] ?? "default" : "default");
  return (
    <span
      className={cn(
        "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium",
        variant === "outline" && "border border-border bg-transparent",
        tones[resolved],
        className,
      )}
      {...props}
    />
  );
}

export function statusTone(status: string): keyof typeof tones {
  if (["approved", "verified", "active", "sent", "meeting_booked", "closed_won",
       "ready"].includes(status))
    return "success";
  if (["rejected", "failed", "dropped", "bounced", "closed_lost",
       "disqualified"].includes(status))
    return "destructive";
  if (["opportunity"].includes(status)) return "primary";
  if (["submitted", "needs_human_review", "flagged", "paused_bounce_rate",
       "paused_manual", "needs_template", "pending_approval", "paused_blacklist"].includes(status))
    return "warning";
  if (["replied", "contacted", "executing"].includes(status)) return "accent";
  return "default";
}
