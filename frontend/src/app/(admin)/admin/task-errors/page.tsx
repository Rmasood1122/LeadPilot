"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api/admin";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";

export default function TaskErrorsPage() {
  const [unresolvedOnly, setUnresolvedOnly] = useState(true);
  const [resolving, setResolving] = useState<string | null>(null);
  const [resolveNote, setResolveNote] = useState("");
  const qc = useQueryClient();

  const { data: errors = [], isLoading } = useQuery({
    queryKey: ["admin", "task-errors", unresolvedOnly],
    queryFn: () => adminApi.listTaskErrors(unresolvedOnly),
  });

  const resolveMutation = useMutation({
    mutationFn: ({ id, note }: { id: string; note: string }) =>
      adminApi.resolveTaskError(id, note),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "task-errors"] });
      setResolving(null);
      setResolveNote("");
      toast.success("Marked as resolved");
    },
    onError: () => toast.error("Failed to resolve"),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Task Errors</h1>
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <Checkbox
            checked={unresolvedOnly}
            onCheckedChange={(v) => setUnresolvedOnly(Boolean(v))}
          />
          Unresolved only
        </label>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading…</div>
      ) : errors.length === 0 ? (
        <div className="rounded-md border p-8 text-center text-muted-foreground">
          No task errors 🎉
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Task</TableHead>
              <TableHead>Error Type</TableHead>
              <TableHead>Message</TableHead>
              <TableHead>Time</TableHead>
              <TableHead>Status</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {errors.map((err: any) => (
              <TableRow key={err.id}>
                <TableCell className="font-mono text-xs max-w-[180px] truncate">
                  {err.task_name.split(".").pop()}
                </TableCell>
                <TableCell>
                  <Badge variant="destructive" className="text-xs">
                    {err.error_type || "Unknown"}
                  </Badge>
                </TableCell>
                <TableCell className="text-sm max-w-[240px] truncate text-muted-foreground">
                  {err.error_message}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground whitespace-nowrap">
                  {new Date(err.ts).toLocaleString()}
                </TableCell>
                <TableCell>
                  {err.resolved_at ? (
                    <Badge variant="outline" className="text-xs text-green-600">Resolved</Badge>
                  ) : (
                    <Badge variant="secondary" className="text-xs">Open</Badge>
                  )}
                </TableCell>
                <TableCell>
                  {!err.resolved_at && (
                    <Button size="sm" variant="outline" onClick={() => setResolving(err.id)}>
                      Resolve
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!resolving} onOpenChange={() => setResolving(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Resolve Task Error</DialogTitle>
          </DialogHeader>
          <Textarea
            placeholder="Resolution note (what was the cause and fix?)…"
            value={resolveNote}
            onChange={(e) => setResolveNote(e.target.value)}
            rows={4}
          />
          <DialogFooter>
            <Button variant="outline" onClick={() => setResolving(null)}>Cancel</Button>
            <Button
              disabled={!resolveNote.trim() || resolveMutation.isPending}
              onClick={() => resolving && resolveMutation.mutate({ id: resolving, note: resolveNote })}
            >
              Mark Resolved
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
