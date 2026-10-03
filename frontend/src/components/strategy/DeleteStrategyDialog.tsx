"use client";

import { useState } from "react";
import { toast } from "sonner";
import { useDeleteStrategy } from "@/lib/api/hooks";
import { deleteStrategyErrorMessage } from "@/lib/api/strategies";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";

/** Password-confirmed, permanent strategy deletion.
 *
 *  The password is checked by the SERVER against the stored hash; this dialog
 *  only collects it. A wrong password leaves the dialog open with the error and
 *  the strategy intact. While the request is in flight the dialog cannot be
 *  dismissed, so "did it delete or not?" never has an ambiguous answer. */
export function DeleteStrategyDialog({
  strategyId,
  open,
  onClose,
  onDeleted,
}: {
  strategyId: string;
  open: boolean;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const deletion = useDeleteStrategy();

  function close() {
    if (deletion.isPending) return;
    setPassword("");
    setError(null);
    onClose();
  }

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!password || deletion.isPending) return;
    setError(null);
    deletion.mutate(
      { id: strategyId, password },
      {
        onSuccess: () => {
          setPassword("");
          toast.success("Strategy deleted.");
          onDeleted();
        },
        onError: (err) => {
          setPassword("");
          setError(deleteStrategyErrorMessage(err));
        },
      },
    );
  }

  return (
    <Modal open={open} onClose={close} title="Delete strategy">
      <form onSubmit={submit} className="space-y-4">
        <p className="text-sm text-muted-foreground">
          This permanently deletes the strategy with its research, leads, sequences and
          campaign history. It cannot be undone.
        </p>
        <div className="space-y-1">
          <Label htmlFor="delete-strategy-password">Enter your password to confirm</Label>
          <Input
            id="delete-strategy-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            disabled={deletion.isPending}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={close} disabled={deletion.isPending}>
            Cancel
          </Button>
          <Button type="submit" variant="destructive" disabled={!password || deletion.isPending}>
            {deletion.isPending ? "Deleting…" : "Delete permanently"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
