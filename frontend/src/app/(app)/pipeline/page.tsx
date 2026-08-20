"use client";

import { useCallback, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { listLeads, updateLeadStatus, deleteLead, getOptin,
         ALLOWED_TRANSITIONS, canTransition } from "@/lib/api/leads";
import { getAccessTokenSync } from "@/lib/auth-session";
import { BASE } from "@/lib/api/client";
import type { LeadOut, LeadStatus } from "@/lib/api/types";
import { AsyncState } from "@/components/ui/skeleton";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ConfirmDialog, Modal } from "@/components/ui/dialog";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

const COLUMNS: { status: LeadStatus; label: string }[] = [
  { status: "sourced",       label: "Sourced"  },
  { status: "enriched",      label: "Enriched" },
  { status: "email_found",   label: "Email found" },
  { status: "verified",      label: "Verified" },
  { status: "flagged",       label: "Flagged"  },
  { status: "contacted",     label: "Contacted"},
  { status: "replied",       label: "Replied"  },
  { status: "meeting_booked",label: "Booked"   },
];

// Pick the first strategy from a tiny listing query so the kanban works
// without a strategy selector in MVP. A future iteration can scope per-strategy.
function useAllLeads() {
  return useQuery({
    queryKey: ["leads", "all"],
    queryFn: async () => {
      const strats = await fetch(
        // Reuse client.ts's BASE rather than re-deriving the origin here —
        // a second copy of the fallback is a second way to ship localhost.
        `${BASE}/strategies`,
        // Was reading the old, removed localStorage key ("leadpilot.access")
        // — a leftover from before client.ts was fixed to route tokens
        // through auth-session.ts (sessionStorage on web / Preferences on
        // native). This always sent an empty Bearer token in production.
        { headers: { Authorization: `Bearer ${getAccessTokenSync() ?? ""}` } },
      ).then(r => r.json()) as { id: string }[];
      if (!strats.length) return [] as LeadOut[];
      const results = await Promise.all(
        strats.slice(0, 5).map(s =>
          listLeads(s.id).then(r => r.items)
        )
      );
      return results.filter(Boolean).flat();
    },
    refetchInterval: 30_000,
  });
}

function LeadDrawer({ lead, onClose }: { lead: LeadOut; onClose: () => void }) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const qc = useQueryClient();
  const toast = useToast();
  const { data: optin } = useQuery({
    queryKey: ["optin", lead.id],
    queryFn: () => getOptin(lead.id),
    retry: false,
  });

  async function handleDelete() {
    try {
      await deleteLead(lead.id);
      toast("Lead deleted (GDPR erasure)", "success");
      qc.invalidateQueries({ queryKey: ["leads"] });
      onClose();
    } catch {
      toast("Could not delete lead", "error");
    }
  }

  return (
    <>
      <Modal open onClose={onClose} title={lead.full_name ?? lead.email ?? "Lead"}>
        <div className="space-y-3 text-sm">
          <p><span className="text-muted-foreground">Title:</span> {lead.title ?? "—"}</p>
          <p><span className="text-muted-foreground">Company:</span> {lead.company ?? "—"}</p>
          <p><span className="text-muted-foreground">Email:</span> {lead.email ?? "—"}</p>
          <p><span className="text-muted-foreground">Phone:</span> {lead.phone ?? "—"}</p>
          <p><span className="text-muted-foreground">Status:</span>{" "}
            <Badge tone={statusTone(lead.status)}>{lead.status}</Badge>
          </p>
          <p>
            <span className="text-muted-foreground">WhatsApp opt-in:</span>{" "}
            {optin ? (
              <Badge tone={optin.current_status === "opted_in" ? "success" : "default"}>
                {optin.current_status}
              </Badge>
            ) : (
              lead.whatsapp_opted_in != null ? (
                <Badge tone={lead.whatsapp_opted_in ? "success" : "default"}>
                  {lead.whatsapp_opted_in ? "opted-in" : "not opted-in"}
                </Badge>
              ) : "—"
            )}
          </p>
          {lead.enrichment_json && Object.keys(lead.enrichment_json).length > 0 && (
            <details className="rounded border border-border p-2">
              <summary className="cursor-pointer font-medium">Enrichment data</summary>
              <pre className="mt-2 max-h-40 overflow-auto text-xs">
                {JSON.stringify(lead.enrichment_json, null, 2)}
              </pre>
            </details>
          )}
          <div className="pt-2">
            <Button variant="destructive" size="sm"
                    onClick={() => setConfirmDelete(true)}>
              Delete (GDPR erasure)
            </Button>
          </div>
        </div>
      </Modal>
      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={handleDelete}
        title="Permanently delete lead?"
        body="This erases all personal data for this contact. This action is irreversible."
        confirmLabel="Delete"
      />
    </>
  );
}

function LeadCard({
  lead,
  onDragStart,
  onClick,
}: {
  lead: LeadOut;
  onDragStart: (e: React.DragEvent) => void;
  onClick: () => void;
}) {
  return (
    <Card
      draggable
      onDragStart={onDragStart}
      onClick={onClick}
      className="cursor-pointer hover:shadow-md active:opacity-70"
      role="button"
      tabIndex={0}
      aria-label={`${lead.full_name ?? lead.email}: ${lead.status}`}
      onKeyDown={(e) => e.key === "Enter" && onClick()}
    >
      <CardContent className="p-3 text-sm">
        <p className="truncate font-medium">{lead.full_name ?? lead.email}</p>
        <p className="truncate text-xs text-muted-foreground">{lead.company}</p>
      </CardContent>
    </Card>
  );
}

export default function PipelinePage() {
  const { data: leads, isLoading, error } = useAllLeads();
  const qc = useQueryClient();
  const toast = useToast();
  const dragRef = useRef<{ lead: LeadOut } | null>(null);
  const [draggingOver, setDraggingOver] = useState<LeadStatus | null>(null);
  const [selected, setSelected] = useState<LeadOut | null>(null);

  const byStatus = useCallback(
    (status: LeadStatus) => (leads ?? []).filter(l => l.status === status),
    [leads],
  );

  async function handleDrop(toStatus: LeadStatus) {
    const fromLead = dragRef.current?.lead;
    setDraggingOver(null);
    if (!fromLead) return;
    if (fromLead.status === toStatus) return;
    if (!canTransition(fromLead.status, toStatus)) {
      toast(`Cannot move from ${fromLead.status} to ${toStatus}`, "error");
      return;
    }
    try {
      await updateLeadStatus(fromLead.id, toStatus);
      qc.invalidateQueries({ queryKey: ["leads"] });
    } catch (err) {
      toast((err as Error).message ?? "Transition rejected", "error");
      qc.invalidateQueries({ queryKey: ["leads"] }); // snap back
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Pipeline</h1>
        <p className="text-sm text-muted-foreground">{leads?.length ?? "—"} leads</p>
      </div>
      <AsyncState isLoading={isLoading} error={error}
                  empty={!leads?.length}
                  emptyLabel="No leads yet. Source leads from a campaign.">
        {/* Horizontal scroll on mobile; full grid on desktop */}
        <div className="flex gap-3 overflow-x-auto pb-4 md:grid md:grid-cols-4 md:overflow-visible lg:grid-cols-8">
          {COLUMNS.map(({ status, label }) => {
            const col = byStatus(status);
            const isDragOver = draggingOver === status;
            return (
              <section
                key={status}
                aria-label={`${label} column`}
                className={cn(
                  "flex min-w-[200px] flex-col gap-2 rounded border border-border bg-muted/40 p-2 transition-colors md:min-w-0",
                  isDragOver && "border-primary bg-primary/5",
                )}
                onDragOver={e => { e.preventDefault(); setDraggingOver(status); }}
                onDragLeave={() => setDraggingOver(null)}
                onDrop={() => handleDrop(status)}
              >
                <div className="flex items-center justify-between px-1">
                  <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    {label}
                  </span>
                  <span className="text-xs text-muted-foreground">{col.length}</span>
                </div>
                {col.map(lead => (
                  <LeadCard
                    key={lead.id}
                    lead={lead}
                    onDragStart={e => {
                      dragRef.current = { lead };
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onClick={() => setSelected(lead)}
                  />
                ))}
              </section>
            );
          })}
        </div>
      </AsyncState>
      {selected && (
        <LeadDrawer lead={selected} onClose={() => setSelected(null)} />
      )}
    </div>
  );
}