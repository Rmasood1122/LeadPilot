"use client";

/** Section E — the public pricing page.
 *
 *  Two ways to pay, side by side: the MONTHLY SUBSCRIPTION (visually marked
 *  Recommended, four tiers) and PAY PER MEETING BOOKED. Every price and limit
 *  comes from GET /billing/catalog, which reads the same module checkout
 *  charges from, so this page cannot advertise a number the product does not
 *  bill or a limit it does not enforce.
 *
 *  Outside the (app) route group: prospects see it without an account. */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CalendarCheck2, Check, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { ApiError, hasSession } from "@/lib/api/client";
import { billingApi } from "@/lib/api/billing";
import { PHONE_NOT_VERIFIED } from "@/lib/identity";
import {
  breakEvenMeetings,
  checkoutNextStep,
  compareOptions,
  featureList,
  formatPrice,
  type MonthlyTier,
} from "@/lib/pricing";
import { Button } from "@/components/ui/button";
import { LogoMark } from "@/components/ui/Logo";
import { cn } from "@/lib/utils";

export default function PricingPage() {
  const router = useRouter();
  const { data: catalog, isLoading, isError } = useQuery({
    queryKey: ["billing", "catalog"],
    queryFn: billingApi.catalog,
    staleTime: 10 * 60 * 1000,
  });
  const [tierId, setTierId] = useState("growth");
  const [meetings, setMeetings] = useState(4);

  const checkout = useMutation({
    mutationFn: (args: { model: "monthly" | "pay_per_meeting"; tier?: string }) =>
      billingApi.checkout(args.model, args.tier),
    onSuccess: (res) => {
      const next = checkoutNextStep(res);
      if (next.kind === "redirect") {
        window.location.assign(next.url);
        return;
      }
      toast.success("Your plan is active.");
      router.push("/settings?billing=success");
    },
    onError: (err) => {
      if (err instanceof ApiError && err.detail === PHONE_NOT_VERIFIED) {
        toast.message("Verify your phone to choose a plan.");
        router.push("/onboarding/verify");
        return;
      }
      toast.error(err instanceof ApiError ? err.detail : "Could not start checkout");
    },
  });

  function choose(model: "monthly" | "pay_per_meeting", tier?: string) {
    if (!hasSession()) {
      router.push("/signup");
      return;
    }
    checkout.mutate({ model, tier });
  }

  const tier: MonthlyTier | undefined = useMemo(
    () => catalog?.monthly.tiers.find((t) => t.id === tierId) ?? catalog?.monthly.tiers[0],
    [catalog, tierId],
  );

  return (
    <main className="min-h-dvh bg-background">
      <header className="mx-auto flex max-w-6xl items-center justify-between p-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <LogoMark size={22} /> LeadPilot
        </Link>
        <Link href={hasSession() ? "/pipeline" : "/login"} className="text-sm underline">
          {hasSession() ? "Back to app" : "Sign in"}
        </Link>
      </header>

      <section className="mx-auto max-w-6xl px-4 pb-16">
        <div className="mx-auto max-w-2xl py-8 text-center">
          <h1 className="text-3xl font-bold tracking-tight md:text-4xl">Pricing that fits how you sell</h1>
          <p className="mt-3 text-muted-foreground">
            A predictable monthly plan, or pay only when a prospect books a meeting.
          </p>
        </div>

        {isLoading && <p className="text-center text-muted-foreground">Loading plans…</p>}
        {isError && <p className="text-center text-destructive">Plans could not be loaded. Refresh to try again.</p>}

        {catalog && tier && (
          <>
            <div className="grid gap-6 lg:grid-cols-[1.6fr_1fr]">
              {/* ── Option 1: Monthly (Recommended) ───────────────────────── */}
              <article
                aria-labelledby="monthly-title"
                className="relative rounded-xl border-2 border-[rgb(var(--primary))] bg-card p-6 shadow-lg"
              >
                <span className="absolute -top-3 left-6 inline-flex items-center gap-1 rounded-full bg-[rgb(var(--primary))] px-3 py-1 text-xs font-semibold text-primary-foreground">
                  <Sparkles size={12} aria-hidden="true" /> Recommended
                </span>
                <h2 id="monthly-title" className="text-xl font-semibold">{catalog.monthly.name}</h2>
                <p className="text-sm text-muted-foreground">
                  Every tier starts with a {catalog.trial_days}-day free trial. Cancel anytime.
                </p>

                <div role="radiogroup" aria-label="Monthly tier" className="mt-5 grid gap-3 sm:grid-cols-2">
                  {catalog.monthly.tiers.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      role="radio"
                      aria-checked={t.id === tier.id}
                      onClick={() => setTierId(t.id)}
                      className={cn(
                        "rounded-lg border p-4 text-left transition-colors",
                        t.id === tier.id
                          ? "border-[rgb(var(--primary))] bg-muted"
                          : "border-border hover:bg-muted/50",
                      )}
                    >
                      <div className="flex items-baseline justify-between">
                        <span className="font-semibold">{t.name}</span>
                        <span className="text-lg font-bold">
                          {formatPrice(t.price_cents, catalog.currency)}
                          <span className="text-xs font-normal text-muted-foreground">/mo</span>
                        </span>
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{t.tagline}</p>
                    </button>
                  ))}
                </div>

                <ul className="mt-5 grid gap-2 text-sm sm:grid-cols-2">
                  {featureList(tier.limits).map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <Check size={16} className="mt-0.5 shrink-0 text-[rgb(var(--primary))]" aria-hidden="true" />
                      {f}
                    </li>
                  ))}
                </ul>

                <Button
                  className="mt-6 w-full"
                  disabled={checkout.isPending}
                  onClick={() => choose("monthly", tier.id)}
                >
                  Start {catalog.trial_days}-day trial of {tier.name}
                </Button>
              </article>

              {/* ── Option 2: Pay per meeting ─────────────────────────────── */}
              <article aria-labelledby="ppm-title" className="rounded-xl border border-border bg-card p-6">
                <h2 id="ppm-title" className="flex items-center gap-2 text-xl font-semibold">
                  <CalendarCheck2 size={20} aria-hidden="true" /> {catalog.pay_per_meeting.name}
                </h2>
                <p className="text-sm text-muted-foreground">{catalog.pay_per_meeting.tagline}</p>
                <p className="mt-5 text-3xl font-bold">
                  {formatPrice(catalog.pay_per_meeting.price_per_meeting_cents, catalog.currency)}
                  <span className="text-sm font-normal text-muted-foreground"> per booked meeting</span>
                </p>
                <p className="text-sm text-muted-foreground">
                  {formatPrice(catalog.pay_per_meeting.monthly_fee_cents, catalog.currency)} monthly fee
                </p>

                <ul className="mt-5 space-y-2 text-sm">
                  {[
                    `Charged ${catalog.pay_per_meeting.grace_hours}h after booking — cancellations are free`,
                    "Billed once per prospect, even if they rebook",
                    ...featureList(catalog.pay_per_meeting.limits),
                  ].map((f) => (
                    <li key={f} className="flex items-start gap-2">
                      <Check size={16} className="mt-0.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                      {f}
                    </li>
                  ))}
                </ul>

                <Button
                  variant="outline"
                  className="mt-6 w-full"
                  disabled={checkout.isPending}
                  onClick={() => choose("pay_per_meeting")}
                >
                  Pay per meeting
                </Button>
              </article>
            </div>

            <ComparisonStrip
              meetings={meetings}
              setMeetings={setMeetings}
              tier={tier}
              perMeetingCents={catalog.pay_per_meeting.price_per_meeting_cents}
              monthlyFeeCents={catalog.pay_per_meeting.monthly_fee_cents}
              currency={catalog.currency}
            />
          </>
        )}
      </section>
    </main>
  );
}

function ComparisonStrip({ meetings, setMeetings, tier, perMeetingCents, monthlyFeeCents, currency }: {
  meetings: number;
  setMeetings: (n: number) => void;
  tier: MonthlyTier;
  perMeetingCents: number;
  monthlyFeeCents: number;
  currency: string;
}) {
  const result = compareOptions(meetings, tier,
    { price_per_meeting_cents: perMeetingCents, monthly_fee_cents: monthlyFeeCents });
  const breakEven = breakEvenMeetings(tier.price_cents, perMeetingCents);
  return (
    <section aria-label="Compare the two options" className="mt-8 rounded-xl border border-border bg-card p-6">
      <label htmlFor="meetings" className="text-sm font-medium">
        Meetings you expect to book per month: <span className="font-bold">{meetings}</span>
      </label>
      <input id="meetings" type="range" min={0} max={30} value={meetings}
             onChange={(e) => setMeetings(Number(e.target.value))} className="mt-2 w-full" />
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <p>{tier.name} monthly: <strong>{formatPrice(result.monthly_cents, currency)}</strong></p>
        <p>Pay per meeting: <strong>{formatPrice(result.pay_per_meeting_cents, currency)}</strong></p>
        <p className="text-muted-foreground">
          {result.cheaper === "same"
            ? "Both cost the same."
            : `${result.cheaper === "monthly" ? tier.name + " monthly" : "Pay per meeting"} saves ${formatPrice(result.savings_cents, currency)}.`}
          {" "}Monthly wins from {breakEven} meetings.
        </p>
      </div>
    </section>
  );
}
