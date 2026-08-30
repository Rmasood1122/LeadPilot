"use client";

/**
 * Admin — the tutorial catalogue (Task 3).
 *
 * This page is the whole point of moving the catalogue out of code: a video
 * goes live by pasting a YouTube id and pressing Publish, with no deploy.
 *
 * It also carries the completion counts that used to be the entire page
 * (Feature 2, FLAG 24). Keeping them here rather than on a separate screen is
 * deliberate — "how many people finished this?" is the question you ask while
 * looking at the tutorial, not in a different tab. Those counts remain
 * AGGREGATE ONLY: the backend returns no user identifier, so this page could
 * not show who watched what even if it tried.
 *
 * Publish is intentionally not a free toggle: the API refuses to publish a
 * tutorial with no youtube_id, because that would put a permanent "coming
 * soon" card in the Learn tab, which reads as broken rather than incomplete.
 * The button is disabled here for the same reason, and the API check is the
 * one that actually enforces it.
 */

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Pencil, Trash2, Youtube } from "lucide-react";
import { adminApi } from "@/lib/api/admin";
import type { AdminTutorial, TutorialLevel } from "@/lib/api/types";
import { ApiError } from "@/lib/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

const LEVEL_TONE: Record<string, "default" | "primary" | "accent"> = {
  beginner: "default",
  intermediate: "primary",
  advanced: "accent",
};

interface EditState {
  slug: string;
  title: string;
  description: string;
  level: TutorialLevel;
  youtube_id: string;
  duration_seconds: string;
  sort_order: string;
}

function toEditState(t: AdminTutorial): EditState {
  return {
    slug: t.slug,
    title: t.title,
    description: t.description,
    level: t.level,
    youtube_id: t.youtube_id ?? "",
    duration_seconds: t.duration_seconds ? String(t.duration_seconds) : "",
    sort_order: String(t.order ?? 0),
  };
}

export default function AdminTutorialsPage() {
  const qc = useQueryClient();
  const [editing, setEditing] = useState<EditState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const list = useQuery({
    queryKey: ["admin", "tutorial-catalogue"],
    queryFn: adminApi.listTutorials,
  });
  const completions = useQuery({
    queryKey: ["admin", "tutorial-completions"],
    queryFn: adminApi.getTutorialCompletions,
  });

  const countsBySlug = useMemo(() => {
    const map = new Map<string, { started: number; completed: number }>();
    for (const row of completions.data?.tutorials ?? []) {
      map.set(row.slug, { started: row.started_count,
                          completed: row.completed_count });
    }
    return map;
  }, [completions.data]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin", "tutorial-catalogue"] });
    qc.invalidateQueries({ queryKey: ["admin", "tutorial-completions"] });
  };
  const onError = (err: unknown) =>
    setError(err instanceof ApiError ? err.detail : "Something went wrong.");

  const save = useMutation({
    mutationFn: (state: EditState) =>
      adminApi.updateTutorial(state.slug, {
        title: state.title,
        description: state.description,
        level: state.level,
        // Empty string means "clear it" -> null, which the API distinguishes
        // from an omitted field. Without that a wrong id could never be removed.
        youtube_id: state.youtube_id.trim() || null,
        duration_seconds: state.duration_seconds.trim()
          ? Number(state.duration_seconds) : null,
        sort_order: Number(state.sort_order) || 0,
      }),
    onSuccess: () => { setEditing(null); setError(null); refresh(); },
    onError,
  });

  const publish = useMutation({
    mutationFn: ({ slug, next }: { slug: string; next: boolean }) =>
      next ? adminApi.publishTutorial(slug) : adminApi.unpublishTutorial(slug),
    onSuccess: () => { setError(null); refresh(); },
    onError,
  });

  const remove = useMutation({
    mutationFn: (slug: string) => adminApi.deleteTutorial(slug),
    onSuccess: (result) => {
      setError(null);
      refresh();
      if (result.progress_rows_kept > 0) {
        setError(`Deleted. ${result.progress_rows_kept} progress row(s) were ` +
                 `KEPT — re-creating this slug restores them.`);
      }
    },
    onError,
  });

  const tutorials = list.data?.tutorials ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Tutorials</h1>
          <p className="text-sm text-muted-foreground">
            Add a YouTube id, then Publish. No deploy required. Unpublished
            tutorials are invisible to users.
          </p>
        </div>
        <div className="shrink-0 rounded border border-border px-4 py-2 text-center">
          <p className="text-xs text-muted-foreground">Published</p>
          <p data-testid="published-count" className="text-2xl font-semibold">
            {list.data ? `${list.data.published_count}/${list.data.total_count}` : "—"}
          </p>
        </div>
      </div>

      {error && (
        <p role="alert" data-testid="admin-tutorial-error"
           className="rounded border border-destructive/40 bg-destructive/5 p-3 text-sm">
          {error}
        </p>
      )}

      {list.isLoading ? (
        <div className="text-muted-foreground">Loading…</div>
      ) : list.error ? (
        <div role="alert" className="rounded border border-destructive/40 p-4 text-sm">
          Could not load the catalogue.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tutorial</TableHead>
              <TableHead>Level</TableHead>
              <TableHead>Video</TableHead>
              <TableHead className="text-right">Started</TableHead>
              <TableHead className="text-right">Completed</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tutorials.map((t) => {
              const counts = countsBySlug.get(t.slug);
              return (
                <TableRow key={t.slug} data-testid={`admin-tutorial-${t.slug}`}>
                  <TableCell>
                    <p className="font-medium">{t.title}</p>
                    <p className="text-xs text-muted-foreground">{t.slug}</p>
                  </TableCell>
                  <TableCell>
                    <Badge tone={LEVEL_TONE[t.level] ?? "default"}>{t.level}</Badge>
                  </TableCell>
                  <TableCell>
                    {t.youtube_id ? (
                      <span className="flex items-center gap-1 text-xs">
                        <Youtube size={13} aria-hidden="true" />
                        {t.youtube_id}
                      </span>
                    ) : (
                      <Badge tone="warning">no video</Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-right">{counts?.started ?? 0}</TableCell>
                  <TableCell className="text-right font-semibold">
                    {counts?.completed ?? 0}
                  </TableCell>
                  <TableCell>
                    <Badge tone={t.is_published ? "success" : "default"}>
                      {t.is_published ? "published" : "draft"}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="outline"
                              aria-label={`Edit ${t.title}`}
                              onClick={() => { setError(null); setEditing(toEditState(t)); }}>
                        <Pencil size={14} />
                      </Button>
                      <Button
                        size="sm"
                        variant={t.is_published ? "outline" : "default"}
                        aria-label={`${t.is_published ? "Unpublish" : "Publish"} ${t.title}`}
                        // Disabled without a video for the same reason the API
                        // returns 409: publishing a placeholder shows users a
                        // permanent "coming soon" card.
                        disabled={(!t.is_published && !t.youtube_id) || publish.isPending}
                        title={!t.is_published && !t.youtube_id
                          ? "Add a YouTube id before publishing" : undefined}
                        onClick={() => publish.mutate({ slug: t.slug,
                                                        next: !t.is_published })}>
                        {t.is_published ? <EyeOff size={14} /> : <Eye size={14} />}
                      </Button>
                      <Button size="sm" variant="outline"
                              aria-label={`Delete ${t.title}`}
                              disabled={remove.isPending}
                              onClick={() => {
                                if (window.confirm(
                                  `Delete "${t.title}"?\n\nUser progress is KEPT — ` +
                                  `re-creating this slug restores it.`)) {
                                  remove.mutate(t.slug);
                                }
                              }}>
                        <Trash2 size={14} />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Edit tutorial</DialogTitle>
          </DialogHeader>
          {editing && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">
                Slug <code>{editing.slug}</code> cannot be changed — renaming it
                would orphan every user&rsquo;s progress for this video.
              </p>
              <div className="space-y-1">
                <Label htmlFor="t-title">Title</Label>
                <Input id="t-title" value={editing.title}
                       onChange={(e) => setEditing({ ...editing, title: e.target.value })} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="t-desc">Description</Label>
                <Textarea id="t-desc" rows={3} value={editing.description}
                          onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="t-yt">YouTube id</Label>
                  <Input id="t-yt" placeholder="e.g. AbCdEfGhIjK"
                         value={editing.youtube_id}
                         onChange={(e) => setEditing({ ...editing, youtube_id: e.target.value })} />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="t-dur">Duration (seconds)</Label>
                  <Input id="t-dur" type="number" min={1}
                         value={editing.duration_seconds}
                         onChange={(e) => setEditing({ ...editing, duration_seconds: e.target.value })} />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="t-level">Level</Label>
                  <select id="t-level"
                          className="h-9 w-full rounded border border-border bg-background px-2 text-sm"
                          value={editing.level}
                          onChange={(e) => setEditing({ ...editing,
                                                        level: e.target.value as TutorialLevel })}>
                    {(list.data?.levels ?? []).map((l) => (
                      <option key={l.level} value={l.level}>{l.label}</option>
                    ))}
                  </select>
                </div>
                <div className="space-y-1">
                  <Label htmlFor="t-order">Sort order</Label>
                  <Input id="t-order" type="number" value={editing.sort_order}
                         onChange={(e) => setEditing({ ...editing, sort_order: e.target.value })} />
                </div>
              </div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button>
            <Button disabled={save.isPending}
                    onClick={() => editing && save.mutate(editing)}>
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
