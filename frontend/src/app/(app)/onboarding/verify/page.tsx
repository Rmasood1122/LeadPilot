"use client";

/** Identity & phone verification (Sections B + C).
 *
 *  Step 1 — where the person is, individual or company, and where the company
 *  is. Step 2 — an SMS code. The Shell sends post-0039 accounts here until both
 *  are done; the phone step can be put off for the session ("Do this later"),
 *  in which case starting outreach, buying a plan and creating share links
 *  still refuse with PHONE_NOT_VERIFIED. */

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MapPin, ShieldCheck, Smartphone } from "lucide-react";

import { ApiError } from "@/lib/api/client";
import { identityApi } from "@/lib/api/identity";
import {
  deferPhone,
  formatCountdown,
  normalizePhone,
  sanitizeCode,
  secondsUntil,
  stepFor,
} from "@/lib/identity";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.detail : fallback;
}

export default function VerifyPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["verification"], queryFn: identityApi.status });
  const countries = useQuery({
    queryKey: ["countries"],
    queryFn: identityApi.countries,
    staleTime: Infinity,
  });

  const step = status.data ? stepFor(status.data) : null;

  useEffect(() => {
    if (status.data && step === null) router.replace("/pipeline");
  }, [status.data, step, router]);

  if (status.isLoading || !status.data) {
    return <p className="p-6 text-sm text-muted-foreground">Loading…</p>;
  }

  return (
    <div className="mx-auto max-w-lg space-y-4 py-6">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <ShieldCheck size={16} aria-hidden="true" />
        <span>Step {step === "phone" ? 2 : 1} of 2 — verify your account</span>
      </div>
      {step === "identity" && (
        <IdentityStep
          countries={countries.data?.countries ?? []}
          initial={status.data}
          onDone={(next) => qc.setQueryData(["verification"], next)}
        />
      )}
      {step === "phone" && (
        <PhoneStep
          onDone={(next) => {
            qc.setQueryData(["verification"], next);
            router.replace("/pipeline");
          }}
          onLater={() => {
            deferPhone();
            router.replace("/pipeline");
          }}
        />
      )}
    </div>
  );
}

function IdentityStep({
  countries,
  initial,
  onDone,
}: {
  countries: { code: string; name: string }[];
  initial: { personal_country: string | null; account_type: string | null;
             company_name: string | null; company_country: string | null };
  onDone: (next: Awaited<ReturnType<typeof identityApi.submitIdentity>>) => void;
}) {
  const [personal, setPersonal] = useState(initial.personal_country ?? "");
  const [kind, setKind] = useState<"individual" | "company">(
    initial.account_type === "company" ? "company" : "individual");
  const [companyName, setCompanyName] = useState(initial.company_name ?? "");
  const [companyCountry, setCompanyCountry] = useState(initial.company_country ?? "");

  const submit = useMutation({
    mutationFn: () =>
      identityApi.submitIdentity({
        personal_country: personal,
        account_type: kind,
        company_name: kind === "company" ? companyName || null : null,
        company_country: kind === "company" ? companyCountry || null : null,
      }),
    onSuccess: onDone,
  });

  const ready = personal && (kind === "individual" || companyCountry);
  const options = useMemo(
    () => countries.map((c) => <option key={c.code} value={c.code}>{c.name}</option>),
    [countries],
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <MapPin size={18} aria-hidden="true" /> Where are you based?
        </CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (ready) submit.mutate();
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="personal-country">Which country are you personally located in?</Label>
            <NativeSelect id="personal-country" required value={personal}
                          onChange={(e) => setPersonal(e.target.value)}>
              <option value="" disabled>Choose a country</option>
              {options}
            </NativeSelect>
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">Are you signing up as an individual or a company?</legend>
            <div className="grid grid-cols-2 gap-2">
              {(["individual", "company"] as const).map((value) => (
                <label key={value}
                       className={`flex cursor-pointer items-center justify-center rounded border px-3 py-2 text-sm capitalize ${
                         kind === value ? "border-[rgb(var(--primary))] bg-muted font-medium" : "border-border"}`}>
                  <input type="radio" name="account-type" value={value} className="sr-only"
                         checked={kind === value} onChange={() => setKind(value)} />
                  {value}
                </label>
              ))}
            </div>
          </fieldset>

          {kind === "company" && (
            <>
              <div className="space-y-1">
                <Label htmlFor="company-name">Company name (optional)</Label>
                <Input id="company-name" maxLength={200} value={companyName}
                       onChange={(e) => setCompanyName(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="company-country">
                  Which country is the company registered or operating in?
                </Label>
                <NativeSelect id="company-country" required value={companyCountry}
                              onChange={(e) => setCompanyCountry(e.target.value)}>
                  <option value="" disabled>Choose a country</option>
                  {options}
                </NativeSelect>
                <p className="text-xs text-muted-foreground">
                  This can be different from where you are.
                </p>
              </div>
            </>
          )}

          {submit.isError && (
            <p role="alert" className="text-sm text-destructive">
              {errorText(submit.error, "Could not save your answers")}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={!ready || submit.isPending}>
            {submit.isPending ? "Saving…" : "Continue"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function PhoneStep({
  onDone,
  onLater,
}: {
  onDone: (next: Awaited<ReturnType<typeof identityApi.verifyCode>>) => void;
  onLater: () => void;
}) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [resendAt, setResendAt] = useState<string | null>(null);
  const [wait, setWait] = useState(0);

  useEffect(() => {
    setWait(secondsUntil(resendAt));
    if (!resendAt) return;
    const timer = window.setInterval(() => setWait(secondsUntil(resendAt)), 1000);
    return () => window.clearInterval(timer);
  }, [resendAt]);

  const normalized = normalizePhone(phone);
  const send = useMutation({
    mutationFn: () => identityApi.sendCode(normalized ?? phone),
    onSuccess: (res) => {
      setSentTo(res.phone_number_masked);
      setResendAt(res.resend_available_at);
      setCode("");
    },
  });
  const verify = useMutation({ mutationFn: () => identityApi.verifyCode(code), onSuccess: onDone });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-lg">
          <Smartphone size={18} aria-hidden="true" /> Verify your phone
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); send.mutate(); }}>
          <Label htmlFor="phone">Mobile number</Label>
          <div className="flex gap-2">
            <Input id="phone" type="tel" inputMode="tel" autoComplete="tel"
                   placeholder="+14155550123" value={phone}
                   onChange={(e) => setPhone(e.target.value)} />
            <Button type="submit" variant="outline"
                    disabled={!normalized || send.isPending || wait > 0}>
              {wait > 0 ? `Resend in ${formatCountdown(wait)}` : sentTo ? "Resend" : "Send code"}
            </Button>
          </div>
          {phone && !normalized && (
            <p className="text-xs text-muted-foreground">
              Include your country code, e.g. +44 20 7946 0958.
            </p>
          )}
          {send.isError && (
            <p role="alert" className="text-sm text-destructive">
              {errorText(send.error, "Could not send the code")}
            </p>
          )}
        </form>

        {sentTo && (
          <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); verify.mutate(); }}>
            <Label htmlFor="code">Enter the 6-digit code we sent to {sentTo}</Label>
            <Input id="code" inputMode="numeric" autoComplete="one-time-code" maxLength={6}
                   value={code} onChange={(e) => setCode(sanitizeCode(e.target.value))}
                   className="tracking-[0.4em]" />
            {verify.isError && (
              <p role="alert" className="text-sm text-destructive">
                {errorText(verify.error, "Could not verify the code")}
              </p>
            )}
            <Button type="submit" className="w-full" disabled={code.length !== 6 || verify.isPending}>
              {verify.isPending ? "Verifying…" : "Verify"}
            </Button>
          </form>
        )}

        <button type="button" onClick={onLater}
                className="w-full text-center text-sm text-muted-foreground underline">
          Do this later
        </button>
        <p className="text-xs text-muted-foreground">
          Until your phone is verified you can explore and research, but not launch
          outreach, choose a paid plan or share dashboards.
        </p>
      </CardContent>
    </Card>
  );
}
