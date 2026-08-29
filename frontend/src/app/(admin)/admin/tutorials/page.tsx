"use client";

/**
 * Admin — tutorial completion counts (Feature 2, FLAG 24).
 *
 * AGGREGATE ONLY, and that is a product decision, not an oversight: an admin
 * sees how many people finished each video, never which videos a named person
 * watched. The backend enforces it by returning no user identifier at all
 * (`GET /admin/tutorials/completions`), so this page could not display one
 * even if it tried.
 */

import { useQuery } from "@tanstack/react-query";
import { adminApi } from "@/lib/api/admin";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const LEVEL_TONE: Record<string, "default" | "primary" | "accent"> = {
  beginner: "default",
  intermediate: "primary",
  advanced: "accent",
};

export default function AdminTutorialsPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "tutorial-completions"],
    queryFn: adminApi.getTutorialCompletions,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Tutorials</h1>
        <p className="text-sm text-muted-foreground">
          Completion counts across all users. Individual watch history is
          private and is not available here.
        </p>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading…</div>
      ) : error ? (
        <div role="alert" className="rounded border border-destructive/40 p-4 text-sm">
          Could not load completion counts.
        </div>
      ) : data ? (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <StatCard label="Active learners" value={data.active_learners}
                      hint="Users with any tutorial progress" />
            <StatCard label="Total completions" value={data.total_completions}
                      hint="Across every tutorial" />
            <StatCard label="Tutorials" value={data.tutorials.length}
                      hint="In the catalogue" />
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Tutorial</TableHead>
                <TableHead>Level</TableHead>
                <TableHead className="text-right">Started</TableHead>
                <TableHead className="text-right">In progress</TableHead>
                <TableHead className="text-right">Completed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.tutorials.map((row) => (
                <TableRow key={row.slug} data-testid={`admin-tutorial-${row.slug}`}>
                  <TableCell className="font-medium">{row.title}</TableCell>
                  <TableCell>
                    <Badge tone={LEVEL_TONE[row.level] ?? "default"}>
                      {row.level}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">{row.started_count}</TableCell>
                  <TableCell className="text-right">{row.in_progress_count}</TableCell>
                  <TableCell className="text-right font-semibold">
                    {row.completed_count}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, hint }: {
  label: string; value: number; hint: string;
}) {
  return (
    <div className="rounded border border-border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-2xl font-semibold">{value}</p>
      <p className="text-xs text-muted-foreground">{hint}</p>
    </div>
  );
}
