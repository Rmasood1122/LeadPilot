"use client";

/**
 * Choose a new password from an emailed reset link
 * (docs/features/password-reset.md).
 *
 * The link is /reset-password#token=<token>. The token is read from the
 * fragment once, kept in memory only, and stripped from the address bar
 * straight away (history.replaceState), so it does not linger in browser
 * history or a screenshot. A fragment is never sent to any server.
 *
 * Success signs the account out everywhere on the server (every session and
 * every older token refused, every personal API key revoked), so any session
 * this browser held is cleared locally too, and the person signs in again.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { KeyRound } from "lucide-react";
import { confirmPasswordReset } from "@/lib/api/auth";
import { clearSession } from "@/lib/api/client";
import { readResetToken, resetErrorMessage, validateNewPassword } from "@/lib/passwordReset";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";

export default function ResetPasswordPage() {
  // undefined = not read yet; null = no usable token in the link.
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setToken(readResetToken(window.location.hash, window.location.search));
    window.history.replaceState(null, "", window.location.pathname);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const invalid = validateNewPassword(password, confirm);
    if (invalid) {
      setError(invalid);
      return;
    }
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      await confirmPasswordReset(token, password);
      clearSession();
      setDone(true);
    } catch (err) {
      setError(resetErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          <KeyRound size={36} className="mb-2 text-[rgb(var(--primary))]" aria-hidden="true" />
          <CardTitle className="text-xl">Choose a new password</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {token === undefined ? (
            <p role="status" className="text-sm text-muted-foreground">Reading your link…</p>
          ) : done ? (
            <div className="space-y-4 text-center">
              <p role="status" className="text-sm">
                Your password has been changed. You have been signed out on every device and
                your personal API keys have been revoked; create new ones in Settings if an
                integration needs them.
              </p>
              <Link href="/login" className="text-sm text-[rgb(var(--primary))] underline">
                Sign in with your new password
              </Link>
            </div>
          ) : token === null ? (
            <div className="space-y-4 text-center">
              <p role="alert" className="text-sm text-destructive">
                This reset link is incomplete. Open the link from the email again, or request a
                new one.
              </p>
              <Link href="/forgot-password" className="text-sm text-[rgb(var(--primary))] underline">
                Request a new link
              </Link>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="new-password">New password</Label>
                <Input id="new-password" type="password" autoComplete="new-password" required
                       value={password} onChange={(e) => setPassword(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="confirm-password">Repeat new password</Label>
                <Input id="confirm-password" type="password" autoComplete="new-password" required
                       value={confirm} onChange={(e) => setConfirm(e.target.value)} />
              </div>
              <p className="text-xs text-muted-foreground">At least 8 characters.</p>
              {error && (
                <p role="alert" className="text-sm text-destructive">
                  {error}{" "}
                  {error.startsWith("This reset link") && (
                    <Link href="/forgot-password" className="underline">Request a new link</Link>
                  )}
                </p>
              )}
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? "Saving…" : "Set new password"}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </main>
  );
}
