"use client";

/** Connector consent: "Claude wants to connect to your Vectorae account".
 *  Reached from GET /oauth/authorize (app/api/oauth.py). Shows who is asking,
 *  where the browser will be sent back to and what access is granted; the
 *  person approves or declines. docs/features/mcp-connector.md. */

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { me } from "@/lib/api/auth";
import { ApiError, restoreSession } from "@/lib/api/client";
import { decideConsent, getConsentRequest, type ConsentRequest } from "@/lib/api/oauth";
import { isRequestId, isSafeClientRedirect, rememberConsentRequest } from "@/lib/oauthConsent";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LogoLockup } from "@/components/ui/Logo";

export default function OAuthConsentPage() {
  const router = useRouter();
  const [request, setRequest] = useState<ConsentRequest | null>(null);
  const [email, setEmail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    const id = new URLSearchParams(window.location.search).get("request");
    if (!isRequestId(id)) {
      setError("This connection link is not valid. Start connecting again from Claude or ChatGPT.");
      return;
    }
    (async () => {
      try {
        if (!(await restoreSession())) {
          rememberConsentRequest(id);
          router.replace("/login");
          return;
        }
        const [user, pending] = await Promise.all([me(), getConsentRequest(id)]);
        if (!mounted) return;
        setEmail(user.email);
        setRequest(pending);
      } catch (err) {
        if (mounted) {
          setError(err instanceof ApiError ? err.detail : "Could not load this connection request.");
        }
      }
    })();
    return () => {
      mounted = false;
    };
  }, [router]);

  async function answer(approve: boolean) {
    if (!request) return;
    setBusy(true);
    setError(null);
    try {
      const { redirect_to } = await decideConsent(request.request_id, approve);
      if (!isSafeClientRedirect(redirect_to)) {
        setError("The app asked to return to an address Vectorae does not allow.");
        setBusy(false);
        return;
      }
      window.location.assign(redirect_to);
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : "Could not record your answer.");
      setBusy(false);
    }
  }

  const appName = request?.client_name || request?.redirect_host || "An app";

  return (
    <main className="flex min-h-dvh items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <LogoLockup width={132} className="mb-2" />
          <CardTitle className="text-xl">
            {request ? `${appName} wants to connect to Vectorae` : "Connect an app"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {!request && !error && (
            <p role="status" className="text-sm text-muted-foreground">Loading…</p>
          )}
          {request && (
            <>
              <p className="text-sm">
                Signed in as <strong>{email}</strong>. After you answer, you return to{" "}
                <strong>{request.redirect_host}</strong>.
              </p>
              <div>
                <p className="text-sm font-medium">It will be able to:</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                  {request.scopes.map((s) => (
                    <li key={s.scope}>{s.description}</li>
                  ))}
                </ul>
              </div>
              <p className="text-xs text-muted-foreground">
                It acts only on your own account. Nothing is sent or scheduled to your
                prospects from this connection. You can disconnect it at any time from the app.
              </p>
              <div className="flex gap-2">
                <Button type="button" variant="outline" className="flex-1" disabled={busy}
                        onClick={() => answer(false)}>
                  Decline
                </Button>
                <Button type="button" className="flex-1" disabled={busy}
                        onClick={() => answer(true)}>
                  {busy ? "Working…" : "Allow"}
                </Button>
              </div>
            </>
          )}
          {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        </CardContent>
      </Card>
    </main>
  );
}
