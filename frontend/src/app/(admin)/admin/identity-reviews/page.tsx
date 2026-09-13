"use client";

/** Section B — the identity review queue. A declared-vs-detected country
 *  mismatch at onboarding lands here; it never blocked the signup. Clearing or
 *  confirming a review does not suspend anyone — that stays the explicit
 *  action on the Users page. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { adminApi, type IdentityReview } from "@/lib/api/admin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const FILTERS = ["pending", "cleared", "confirmed_risk", "all"] as const;

export default function IdentityReviewsPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<(typeof FILTERS)[number]>("pending");
  const [notes, setNotes] = useState<Record<string, string>>({});

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "identity-reviews", filter],
    queryFn: () => adminApi.listIdentityReviews(filter),
  });

  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "cleared" | "confirmed_risk" }) =>
      adminApi.decideIdentityReview(id, decision, notes[id] ?? ""),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "identity-reviews"] });
      toast.success("Review recorded");
    },
    onError: () => toast.error("Could not record the decision"),
  });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-2xl font-bold">Identity reviews</h1>
          <p className="text-sm text-muted-foreground">
            {data?.pending_count ?? 0} pending — declared country did not match the signup network.
          </p>
        </div>
        <NativeSelect className="w-48" value={filter}
                      onChange={(e) => setFilter(e.target.value as (typeof FILTERS)[number])}>
          {FILTERS.map((f) => <option key={f} value={f}>{f.replace("_", " ")}</option>)}
        </NativeSelect>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading…</div>
      ) : !data?.reviews.length ? (
        <div className="text-muted-foreground">Nothing to review.</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Account</TableHead>
              <TableHead>Declared</TableHead>
              <TableHead>Detected</TableHead>
              <TableHead>Company</TableHead>
              <TableHead>Phone</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.reviews.map((r: IdentityReview) => (
              <TableRow key={r.user_id}>
                <TableCell className="font-medium">
                  {r.email}
                  <div className="text-xs text-muted-foreground">{r.signup_ip ?? "—"}</div>
                </TableCell>
                <TableCell>{r.personal_country ?? "—"}</TableCell>
                <TableCell>{r.geo_detected_country ?? "—"}</TableCell>
                <TableCell className="text-sm">
                  {r.account_type === "company"
                    ? `${r.company_name ?? "Unnamed"} (${r.company_country ?? "—"})`
                    : "Individual"}
                </TableCell>
                <TableCell>
                  <Badge variant={r.phone_verified ? "secondary" : "outline"}>
                    {r.phone_verified ? "Verified" : "Unverified"}
                  </Badge>
                </TableCell>
                <TableCell>
                  <Badge variant={r.geo_review_status === "confirmed_risk" ? "destructive" : "secondary"}>
                    {r.geo_review_status?.replace("_", " ")}
                  </Badge>
                  {r.geo_reviewed_by && (
                    <div className="text-xs text-muted-foreground">by {r.geo_reviewed_by}</div>
                  )}
                </TableCell>
                <TableCell className="min-w-[16rem] space-y-2">
                  {r.geo_review_status === "pending" ? (
                    <>
                      <Input placeholder="Note (optional)" value={notes[r.user_id] ?? ""}
                             onChange={(e) => setNotes((n) => ({ ...n, [r.user_id]: e.target.value }))} />
                      <div className="flex gap-2">
                        <Button size="sm" variant="outline" disabled={decide.isPending}
                                onClick={() => decide.mutate({ id: r.user_id, decision: "cleared" })}>
                          Clear
                        </Button>
                        <Button size="sm" variant="destructive" disabled={decide.isPending}
                                onClick={() => decide.mutate({ id: r.user_id, decision: "confirmed_risk" })}>
                          Confirm risk
                        </Button>
                      </div>
                    </>
                  ) : (
                    <span className="text-xs text-muted-foreground">{r.geo_review_note ?? ""}</span>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
