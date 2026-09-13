"use client";

/** Feature A2 — the tamper-evident activity audit trail.
 *  Verify the hash chain and download a signed report (JSON is the signed
 *  artefact; the PDF is the same report for humans) to hand an enterprise
 *  buyer as proof of activity. */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Download, ShieldCheck } from "lucide-react";

import { downloadAuditExport, verifyAuditTrail } from "@/lib/api/audit";
import { exportFilename, verificationSummary, type ChainVerification } from "@/lib/audit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export function AuditTrailCard() {
  const [result, setResult] = useState<ChainVerification | null>(null);
  const verify = useMutation({ mutationFn: verifyAuditTrail, onSuccess: setResult });
  const download = useMutation({
    mutationFn: async (format: "json" | "pdf") => {
      const blob = await downloadAuditExport(format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = exportFilename(format);
      link.click();
      URL.revokeObjectURL(url);
    },
  });
  const summary = verificationSummary(result);

  return (
    <div className="space-y-4 rounded-lg border bg-card p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 font-semibold">
            <ShieldCheck size={16} aria-hidden="true" /> Activity audit trail
          </h3>
          <p className="text-sm text-muted-foreground">
            Every send, open, click, reply and booked meeting, hash-chained so any edit or
            deletion is detectable. Exports are signed.
          </p>
        </div>
        <Badge tone={summary.tone}>{summary.label}</Badge>
      </div>
      {summary.detail && <p className="text-xs text-muted-foreground">{summary.detail}</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" disabled={verify.isPending} onClick={() => verify.mutate()}>
          {verify.isPending ? "Verifying…" : "Verify chain"}
        </Button>
        <Button size="sm" variant="outline" disabled={download.isPending}
                onClick={() => download.mutate("json")}>
          <Download size={14} aria-hidden="true" /> Signed JSON
        </Button>
        <Button size="sm" variant="outline" disabled={download.isPending}
                onClick={() => download.mutate("pdf")}>
          <Download size={14} aria-hidden="true" /> PDF report
        </Button>
      </div>
      {(verify.isError || download.isError) && (
        <p role="alert" className="text-sm text-destructive">
          {((verify.error ?? download.error) as Error)?.message ?? "Something went wrong"}
        </p>
      )}
    </div>
  );
}
