"use client";

/**
 * "Check your email" — where a signed-up-but-unverified account waits.
 *
 * Reached from three places:
 *   • straight after signup
 *   • after a login by an account that is not verified yet
 *   • from Shell.tsx, when any dashboard request comes back 403
 *     EMAIL_NOT_VERIFIED (e.g. a bookmarked /pipeline opened in a new tab)
 *
 * The address is read from ?email= rather than from a store, so the page works
 * on a cold load in a new tab. It falls back to GET /auth/me... which cannot
 * work for an unverified account (that is the whole point of the gate), so the
 * real fallback is the resend form's own input.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { MailCheck } from "lucide-react";
import { resendVerification } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

export default function CheckEmailPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [sendFailed, setSendFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // window.location rather than useSearchParams(): this is a static export
  // (next.config.js output:'export'), where useSearchParams forces the page
  // into a Suspense boundary at build time. Reading the query in an effect is
  // equivalent here and keeps `next build` from failing on a prerender rule.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setEmail(params.get("email") ?? "");
    setSendFailed(params.get("sent") === "false");
  }, []);

  async function resend(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await resendVerification(email);
      setSent(true);
    } catch (err) {
      // 429 is the one failure worth showing verbatim: it tells the user to
      // wait rather than to keep clicking.
      setError(
        err instanceof ApiError
          ? err.status === 429
            ? "Too many requests. Wait a few minutes and try again."
            : err.detail
          : "Could not send the email. Try again shortly.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <MailCheck size={40} className="mb-2 text-[rgb(var(--primary))]"
                     aria-hidden="true" />
          <CardTitle className="text-xl">Check your email</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {sendFailed ? (
            <p role="alert" className="text-sm text-destructive">
              Your account was created, but we could not send the verification
              email just now. Press the button below to try again.
            </p>
          ) : (
            <p className="text-sm text-muted-foreground">
              We sent a verification link
              {email ? <> to <strong>{email}</strong></> : null}. Click it to
              activate your account. The link expires in 24 hours.
            </p>
          )}

          <p className="text-sm text-muted-foreground">
            Nothing arrived? Check your spam folder, then request a new link.
          </p>

          <form onSubmit={resend} className="space-y-3 border-t border-border pt-4">
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setSent(false);
                }}
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-destructive">{error}</p>
            )}
            {sent && (
              <p role="status" className="text-sm text-[rgb(var(--primary))]">
                {/* Deliberately hedged. The backend answers 202 whether or not
                    the address has an account, so promising "sent" outright
                    would turn this screen into an account-existence oracle. */}
                If that address has an unverified account, a new link is on its
                way.
              </p>
            )}
            <Button type="submit" className="w-full" disabled={busy || !email}>
              {busy ? "Sending…" : "Resend verification email"}
            </Button>
          </form>

          <p className="text-center text-sm text-muted-foreground">
            Already verified?{" "}
            <Link href="/login" className="text-[rgb(var(--primary))] underline">
              Sign in
            </Link>
          </p>
          <button
            type="button"
            onClick={() => router.replace("/login")}
            className="w-full text-center text-xs text-muted-foreground underline"
          >
            Use a different account
          </button>
        </CardContent>
      </Card>
    </main>
  );
}
