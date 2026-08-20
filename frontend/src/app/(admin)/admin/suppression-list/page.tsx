"use client";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { adminApi } from "@/lib/api/admin";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";

export default function SuppressionListPage() {
  const [addOpen, setAddOpen] = useState(false);
  const [email, setEmail] = useState("");
  const [reason, setReason] = useState("");
  const [search, setSearch] = useState("");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["admin", "suppression-list"],
    queryFn: () => adminApi.listSuppression(),
  });

  const addMutation = useMutation({
    mutationFn: () => adminApi.addSuppression(email, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "suppression-list"] });
      setAddOpen(false);
      setEmail("");
      setReason("");
      toast.success("Added to suppression list");
    },
    onError: () => toast.error("Failed to add"),
  });

  const removeMutation = useMutation({
    mutationFn: (e: string) => adminApi.removeSuppression(e),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "suppression-list"] });
      toast.success("Removed from suppression list");
    },
    onError: () => toast.error("Failed to remove"),
  });

  const items: any[] = data?.items ?? [];
  const filtered = items.filter((item) =>
    !search || item.email?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Suppression List</h1>
          <p className="text-sm text-muted-foreground mt-1">
            {data?.total ?? 0} total entries
          </p>
        </div>
        <div className="flex gap-2">
          <Input
            placeholder="Filter email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-56"
          />
          <Button onClick={() => setAddOpen(true)}>Add Entry</Button>
        </div>
      </div>

      {isLoading ? (
        <div className="text-muted-foreground">Loading…</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Email / Phone</TableHead>
              <TableHead>Reason</TableHead>
              <TableHead>Source</TableHead>
              <TableHead>Added</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.map((item: any) => (
              <TableRow key={item.id}>
                <TableCell className="font-mono text-sm">{item.email || item.phone}</TableCell>
                <TableCell className="text-sm text-muted-foreground">{item.reason}</TableCell>
                <TableCell className="text-sm">{item.source}</TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {new Date(item.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    disabled={removeMutation.isPending}
                    onClick={() => item.email && removeMutation.mutate(item.email)}
                  >
                    Remove
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>Add to Suppression List</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <Input
              placeholder="Email address"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <Input
              placeholder="Reason (e.g. 'manual opt-out')"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddOpen(false)}>Cancel</Button>
            <Button
              disabled={!email.trim() || !reason.trim() || addMutation.isPending}
              onClick={() => addMutation.mutate()}
            >
              Add
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
