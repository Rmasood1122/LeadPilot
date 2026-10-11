"use client";

/**
 * "Forgot password?" — ask for a reset link (docs/features/password-reset.md).
 *
 * The confirmation is the same for every address: the API answers 200 whether
 * or not the address has an account, so this page cannot be used to find out
 * who has one either.
 */

import { useState } from "react";
import Link from "next/link";
import { KeyRound } from "lucide-react";
import { requestPasswordReset } from "@/lib/api/auth";
import { REQUEST_SENT_MESSAGE, requestErrorMessage } from "@/lib/passwordReset";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await requestPasswordReset(email.trim());
      setSent(true);
    } catch (err) {
      setError(requestErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <KeyRound size={36} className="mb-2 text-[rgb(var(--primary))]" aria-hidden="true" />
          <CardTitle className="text-xl">Reset your password</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {sent ? (
            <p role="status" className="text-sm">{REQUEST_SENT_MESSAGE}</p>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <p className="text-sm text-muted-foreground">
                Enter the email address you sign in with and we will email you a link to choose a
                new password.
              </p>
              <div className="space-y-1">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" autoComplete="email" required value={email}
                       onChange={(e) => setEmail(e.target.value)} />
              </div>
              {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Sending…" : "Email me a reset link"}
              </Button>
            </form>
          )}
          <p className="text-center text-sm text-muted-foreground">
            <Link href="/login" className="text-[rgb(var(--primary))] underline">
              Back to sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </main>
  );
}
