"use client";

/** Your LinkedIn network: upload your own export, see who is relevant to what
 *  you sell. Private to this account. Growth plan and up. */
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api/client";
import {
  eraseNetwork, getNetworkStatus, getRecommendations, importConnections,
} from "@/lib/api/network";
import {
  checkExportFile, importErrorMessage, importSummary, safeProfileUrl, scoreLabel,
} from "@/lib/linkedinNetwork";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function NetworkPage() {
  const qc = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const status = useQuery({ queryKey: ["network-status"], queryFn: getNetworkStatus });
  const eligible = status.data?.eligible === true;
  const recs = useQuery({
    queryKey: ["network-recs"], queryFn: getRecommendations,
    enabled: eligible && (status.data?.connection_count ?? 0) > 0,
  });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["network-status"] });
    qc.invalidateQueries({ queryKey: ["network-recs"] });
  };

  const upload = useMutation({
    mutationFn: importConnections,
    onSuccess: (r) => { setError(null); setMessage(importSummary(r)); refresh(); },
    onError: (e) => { setMessage(null); setError(importErrorMessage(e)); },
  });
  const erase = useMutation({
    mutationFn: eraseNetwork,
    onSuccess: () => { setError(null); setMessage("Your uploaded connections were deleted."); refresh(); },
    onError: (e) => setError(e instanceof ApiError ? e.message : "Delete failed."),
  });

  async function onFile(file: File | undefined) {
    if (!file || !status.data) return;
    const problem = checkExportFile(file, status.data.max_bytes);
    if (problem) { setMessage(null); setError(problem); return; }
    upload.mutate(await file.text());
    if (fileRef.current) fileRef.current.value = "";
  }

  if (status.isLoading) return <p className="p-6 text-sm">Loading…</p>;
  if (status.isError || !status.data) return <p className="p-6 text-sm">Could not load your network.</p>;
  const s = status.data;

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4 md:p-6">
      <header>
        <h1 className="text-xl font-semibold">Your LinkedIn network</h1>
        <p className="text-sm text-muted-foreground">
          Private to your account. Nobody else can see these connections, and yours are never
          shown to anyone else.
        </p>
      </header>

      {!eligible && (
        <Card>
          <CardContent className="space-y-2 pt-6 text-sm">
            <p>
              The LinkedIn network is included with the Growth plan and higher. You are on{" "}
              <strong>{s.plan}</strong>.
            </p>
            <a className="underline" href="/settings">Upgrade in Settings</a>
          </CardContent>
        </Card>
      )}

      {eligible && (
        <Card>
          <CardHeader><CardTitle>Upload your connections</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <ol className="list-decimal space-y-1 pl-5">
              <li>On LinkedIn: Settings &amp; Privacy → Data privacy → Get a copy of your data.</li>
              <li>Choose <strong>Connections</strong> and request the archive.</li>
              <li>Upload the <code>Connections.csv</code> file from it here.</li>
            </ol>
            <p className="text-muted-foreground">
              Only name, job title, company, profile link and connection date are stored. Email
              addresses in the file are ignored. LinkedIn has no feed for new connections, so
              upload a fresh export when your network has grown; scores are refreshed weekly.
            </p>
            <input ref={fileRef} type="file" accept=".csv,text/csv"
                   aria-label="Connections.csv"
                   onChange={(e) => onFile(e.target.files?.[0])} />
            {upload.isPending && <p>Importing…</p>}
            {s.needs_new_export && (
              <p className="text-amber-600">
                Your export is more than a few weeks old. Upload a fresh one to see new connections.
              </p>
            )}
            <p className="text-muted-foreground">
              {s.connection_count} connection{s.connection_count === 1 ? "" : "s"} stored.
            </p>
            {s.connection_count > 0 && (
              <Button variant="outline" disabled={erase.isPending}
                      onClick={() => { if (window.confirm("Delete all uploaded connections?")) erase.mutate(); }}>
                Delete my uploaded connections
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {message && <p role="status" className="text-sm">{message}</p>}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}

      {eligible && recs.data?.products.map((p) => (
        <Card key={p.product_id}>
          <CardHeader>
            <CardTitle>{p.product_name} — {p.total_matches} relevant</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              {p.segments.map((seg) => (
                <Badge key={seg.segment}>{seg.segment} · {seg.count}</Badge>
              ))}
            </div>
            <ul className="divide-y text-sm">
              {p.matches.map((m) => {
                const link = safeProfileUrl(m.profile_url);
                return (
                  <li key={m.connection_id} className="py-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">
                        {link ? <a href={link} target="_blank" rel="noopener noreferrer">{m.full_name}</a> : m.full_name}
                      </span>
                      <Badge>{scoreLabel(m.score)}</Badge>
                    </div>
                    <div className="text-muted-foreground">
                      {[m.position, m.company].filter(Boolean).join(" · ")}
                    </div>
                    {m.reasons?.length ? (
                      <div className="text-xs text-muted-foreground">{m.reasons.join("; ")}</div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
