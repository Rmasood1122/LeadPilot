"use client";

/** Feature Group 8: accept a workspace invitation (/invite?token=...).
 *  Inside the (app) group, so the Shell sends a signed-out visitor to log in
 *  first; the server then checks the signed-in address matches the invite. */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { acceptInvitation } from "@/lib/api/workspaces";
import { setActiveWorkspace } from "@/lib/workspace";
import { Card, CardContent } from "@/components/ui/card";

export default function InvitePage() {
  const token = useSearchParams().get("token");
  const [state, setState] = useState<{ ok: boolean; text: string } | null>(null);
  const started = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    if (!token) {
      setState({ ok: false, text: "This invitation link is incomplete." });
      return;
    }
    acceptInvitation(token)
      .then((r) => {
        setActiveWorkspace(r.workspace_id);
        setState({ ok: true, text: `You joined ${r.name} as ${r.role}.` });
      })
      .catch((e) => setState({ ok: false, text: (e as Error).message }));
  }, [token]);

  return (
    <Card className="mx-auto max-w-md">
      <CardContent className="space-y-3 p-gutter text-sm">
        <h1 className="text-lg font-semibold">Workspace invitation</h1>
        {!state && <p className="text-muted-foreground">Accepting…</p>}
        {state && (
          <p role={state.ok ? "status" : "alert"}
             className={state.ok ? "" : "text-[rgb(var(--destructive))]"}>
            {state.text}
          </p>
        )}
        {state?.ok && (
          <a href="/pipeline" className="font-medium text-[rgb(var(--primary))] hover:underline">
            Open the workspace →
          </a>
        )}
        {state && !state.ok && (
          <Link href="/team" className="text-[rgb(var(--primary))] hover:underline">
            Go to your team page
          </Link>
        )}
      </CardContent>
    </Card>
  );
}
