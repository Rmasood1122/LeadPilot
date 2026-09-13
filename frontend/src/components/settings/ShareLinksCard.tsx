"use client";

/** Feature A6 — create, copy and revoke read-only ROI dashboard links. The
 *  full link is shown once, right after creation (only a hash is stored). */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Link2 } from "lucide-react";

import { ApiError } from "@/lib/api/client";
import { createShareLink, listShareLinks, revokeShareLink } from "@/lib/api/shareLinks";
import { listStrategies } from "@/lib/api/strategies";
import { PHONE_NOT_VERIFIED } from "@/lib/identity";
import { expiresInText } from "@/lib/shareLinks";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";

export function ShareLinksCard() {
  const qc = useQueryClient();
  const links = useQuery({ queryKey: ["share-links"], queryFn: listShareLinks });
  const strategies = useQuery({ queryKey: ["strategies"], queryFn: listStrategies });
  const [label, setLabel] = useState("ROI dashboard");
  const [scope, setScope] = useState("");
  const [days, setDays] = useState(30);
  const [fresh, setFresh] = useState<string | null>(null);

  const create = useMutation({
    mutationFn: () => createShareLink({ label, strategy_id: scope || null, expires_in_days: days }),
    onSuccess: (res) => {
      setFresh(res.url);
      qc.invalidateQueries({ queryKey: ["share-links"] });
    },
  });
  const revoke = useMutation({
    mutationFn: revokeShareLink,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["share-links"] }),
  });

  const errorText = create.error instanceof ApiError
    ? (create.error.detail === PHONE_NOT_VERIFIED
      ? "Verify your phone number first (Settings → verify)." : create.error.detail)
    : create.isError ? "Could not create the link" : null;

  return (
    <div className="space-y-4 rounded-lg border bg-card p-5">
      <div>
        <h3 className="flex items-center gap-2 font-semibold">
          <Link2 size={16} aria-hidden="true" /> Shareable ROI dashboards
        </h3>
        <p className="text-sm text-muted-foreground">
          A read-only link to pipeline, meetings booked and revenue — no login needed. Links
          expire and can be revoked at any time. No lead names or emails are ever shown.
        </p>
      </div>

      <form className="grid gap-3 sm:grid-cols-4" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="share-label">Title</Label>
          <Input id="share-label" maxLength={120} value={label} onChange={(e) => setLabel(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="share-scope">Shows</Label>
          <NativeSelect id="share-scope" value={scope} onChange={(e) => setScope(e.target.value)}>
            <option value="">All campaigns</option>
            {strategies.data?.map((s) => (
              <option key={s.id} value={s.id}>
                {(s as unknown as { product_name?: string }).product_name ?? s.id.slice(0, 8)}
              </option>
            ))}
          </NativeSelect>
        </div>
        <div className="space-y-1">
          <Label htmlFor="share-days">Expires after</Label>
          <NativeSelect id="share-days" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[7, 30, 90, 365].map((d) => <option key={d} value={d}>{d} days</option>)}
          </NativeSelect>
        </div>
        <div className="sm:col-span-4">
          <Button type="submit" size="sm" disabled={create.isPending}>Create link</Button>
        </div>
      </form>
      {errorText && <p role="alert" className="text-sm text-destructive">{errorText}</p>}

      {fresh && (
        <div className="space-y-1 rounded border border-[rgb(var(--success))] p-3 text-sm">
          <p className="font-medium">Copy this link now — it will not be shown again.</p>
          <div className="flex gap-2">
            <Input readOnly value={fresh} onFocus={(e) => e.target.select()} />
            <Button type="button" size="sm" variant="outline"
                    onClick={() => void navigator.clipboard?.writeText(fresh)}>
              <Copy size={14} aria-hidden="true" /> Copy
            </Button>
          </div>
        </div>
      )}

      <ul className="divide-y divide-border text-sm">
        {links.data?.map((link) => (
          <li key={link.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
            <div className="min-w-0">
              <p className="font-medium">{link.label}</p>
              <p className="text-xs text-muted-foreground">
                {link.scope === "account" ? "All campaigns" : "One campaign"} · {link.token_prefix}… ·{" "}
                {link.view_count} views · {link.status === "active" ? `expires ${expiresInText(link.expires_at)}` : link.status}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={link.status === "active" ? "success" : "default"}>{link.status}</Badge>
              {link.status === "active" && (
                <Button size="sm" variant="ghost" disabled={revoke.isPending}
                        onClick={() => revoke.mutate(link.id)}>Revoke</Button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
