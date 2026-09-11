"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteLead, getOptin } from "@/lib/api/leads";
import type { LeadOut } from "@/lib/api/types";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog, Modal } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";

export function LeadDrawer({
  lead,
  strategyId,
  onClose,
}: {
  lead: LeadOut;
  strategyId: string;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const { data: optin } = useQuery({
    queryKey: ["optin", lead.id],
    queryFn: () => getOptin(lead.id),
    enabled: !!lead.phone,
  });

  async function gdprDelete() {
    try {
      await deleteLead(lead.id);
      toast("Lead and all associated data deleted", "success");
      queryClient.invalidateQueries({ queryKey: ["leads", strategyId] });
      onClose();
    } catch {
      toast("Delete failed", "error");
    }
  }

  const enrichment = Object.entries(lead.enrichment_json ?? {}).filter(
    ([, v]) => typeof v === "string" || typeof v === "number",
  );

  return (
    <Modal open onClose={onClose} title={lead.full_name ?? "Lead"}>
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={statusTone(lead.status)}>{lead.status}</Badge>
          {lead.phone && (
            <Badge tone={optin?.current_status === "opted_in" ? "success" : "default"}>
              WhatsApp: {optin?.current_status ?? "unknown"}
            </Badge>
          )}
        </div>
        <dl className="grid grid-cols-2 gap-2">
          <dt className="text-muted-foreground">Title</dt><dd>{lead.title ?? "—"}</dd>
          <dt className="text-muted-foreground">Company</dt><dd>{lead.company ?? "—"}</dd>
          <dt className="text-muted-foreground">Email</dt><dd className="break-all">{lead.email ?? "—"}</dd>
          <dt className="text-muted-foreground">Phone</dt><dd>{lead.phone ?? "—"}</dd>
        </dl>
        {enrichment.length > 0 && (
          <section aria-label="Enrichment">
            <h3 className="mb-1 font-medium">Enrichment</h3>
            <dl className="grid grid-cols-2 gap-1">
              {enrichment.map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="break-all">{String(v)}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}
        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-3">
          <Link
            href={`/leads/detail?id=${lead.id}`}
            className="inline-flex h-8 items-center rounded border border-border px-3 text-xs font-medium hover:bg-muted"
          >
            Open full lead
          </Link>
          <Button variant="destructive" size="sm" onClick={() => setConfirming(true)}>
            Delete lead (GDPR)
          </Button>
        </div>
      </div>
      <ConfirmDialog
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={gdprDelete}
        title="Delete this lead?"
        body="This permanently removes the lead, their messages, and outcomes. Their contact details are added to the suppression list so they are never contacted again. This cannot be undone."
        confirmLabel="Delete permanently"
      />
    </Modal>
  );
}
