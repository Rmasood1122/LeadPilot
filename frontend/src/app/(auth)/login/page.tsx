"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { login } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label } from "@/components/ui/input";
import { LogoLockup } from "@/components/ui/Logo";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // GET /auth/verify 302s back here with one of these flags. Read from
  // window.location rather than useSearchParams() because this is a static
  // export, where useSearchParams forces a Suspense boundary at build time.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const verified = params.get("verified");
    const err = params.get("error");
    if (verified === "true") {
      setNotice("Email verified. Sign in to continue.");
    } else if (verified === "already") {
      setNotice("That address is already verified. Sign in to continue.");
    } else if (err === "expired") {
      setError(
        "That verification link has expired. Sign in and we will send you a new one.",
      );
    } else if (err === "invalid") {
      setError(
        "That verification link is not valid. Sign in and we will send you a new one.",
      );
    }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const user = await login(email, password);
      // Login SUCCEEDS for an unverified account on purpose -- otherwise there
      // is no signed-in state from which to ask for a new link. The routing
      // decision is made here instead.
      if (user.email_verified === false) {
        router.replace(`/check-email?email=${encodeURIComponent(email)}`);
        return;
      }
      router.replace("/pipeline");
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not sign in");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-sm">
        <CardHeader className="items-center text-center">
          {/* Room here for the full lockup at a size where the wordmark
              actually reads, so the title drops the product name. */}
          <LogoLockup width={132} className="mb-2" />
          <CardTitle className="text-xl">Sign in</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1">
              <Label htmlFor="email">Email</Label>
              <Input id="email" type="email" required value={email}
                     onChange={(e) => setEmail(e.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="password">Password</Label>
              <Input id="password" type="password" required value={password}
                     onChange={(e) => setPassword(e.target.value)} />
            </div>
            {notice && (
              <p role="status" className="text-sm text-[rgb(var(--primary))]">
                {notice}
              </p>
            )}
            {error && (
              <p role="alert" className="text-sm text-destructive">{error}</p>
            )}
            <Button type="submit" className="w-full" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </Button>
            <p className="text-center text-sm text-muted-foreground">
              No account?{" "}
              <Link href="/signup" className="text-[rgb(var(--primary))] underline">
                Sign up
              </Link>
            </p>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
