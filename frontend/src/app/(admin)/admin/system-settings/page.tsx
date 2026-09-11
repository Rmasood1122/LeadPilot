"use client";

/** Admin > System Settings: the feature switches and limits the feature
 *  expansion reads at run time (app/services/system_settings.py). A change
 *  takes effect on the next request or task -- no deploy, no restart. The
 *  server refuses a value whose type does not match the setting's default. */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  listSystemSettings,
  updateSystemSetting,
  type SystemSetting,
} from "@/lib/api/systemAdmin";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";

export default function AdminSystemSettingsPage() {
  const query = useQuery({
    queryKey: ["admin", "system-settings"],
    queryFn: listSystemSettings,
  });

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-bold">System Settings</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Deployment-wide switches and limits. Changes apply immediately.
        </p>
      </div>
      {query.isLoading && <div className="text-muted-foreground">Loading…</div>}
      {query.error && <div className="text-destructive">{(query.error as Error).message}</div>}
      {query.data && (
        <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Setting</TableHead>
                <TableHead className="w-72">Value</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {query.data.map((setting) => (
                <SettingRow key={setting.key} setting={setting} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}

function SettingRow({ setting }: { setting: SystemSetting }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState(String(setting.value));
  useEffect(() => setDraft(String(setting.value)), [setting.value]);

  const save = useMutation({
    mutationFn: (value: SystemSetting["value"]) => updateSystemSetting(setting.key, value),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "system-settings"] });
      toast.success(`${setting.key} updated`);
    },
    onError: (e) => toast.error((e as Error).message),
  });

  const parsed: SystemSetting["value"] | null =
    setting.type === "int"
      ? /^\d+$/.test(draft.trim()) ? Number(draft) : null
      : setting.type === "float"
        ? draft.trim() !== "" && Number.isFinite(Number(draft)) ? Number(draft) : null
        : draft.trim() || null;

  return (
    <TableRow>
      <TableCell>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-sm">{setting.key}</span>
          {setting.is_default && <Badge>default</Badge>}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{setting.description}</p>
      </TableCell>
      <TableCell>
        {setting.type === "bool" ? (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={Boolean(setting.value)}
              disabled={save.isPending}
              onChange={(e) => save.mutate(e.target.checked)}
            />
            {setting.value ? "On" : "Off"}
          </label>
        ) : (
          <div className="flex gap-2">
            <Input
              value={draft}
              inputMode={setting.type === "str" ? "text" : "decimal"}
              onChange={(e) => setDraft(e.target.value)}
              aria-invalid={parsed === null}
            />
            <Button
              size="sm"
              disabled={parsed === null || draft === String(setting.value) || save.isPending}
              onClick={() => parsed !== null && save.mutate(parsed)}
            >
              Save
            </Button>
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}
