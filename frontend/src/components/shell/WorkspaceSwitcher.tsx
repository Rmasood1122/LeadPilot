"use client";

/** Feature Group 8: which workspace the app is acting in.
 *
 *  Switching reloads the page: every cached query belongs to the previous
 *  workspace's data, and a reload is the one way to be sure none of it
 *  survives into the next. */

import { useQuery } from "@tanstack/react-query";
import { listMemberships } from "@/lib/api/workspaces";
import { ROLE_LABELS, getActiveWorkspace, setActiveWorkspace } from "@/lib/workspace";

export function WorkspaceSwitcher() {
  const { data } = useQuery({ queryKey: ["memberships"], queryFn: listMemberships });
  if (!data || data.length < 2) return null;

  const personal = data.find((w) => w.is_personal);
  const active = getActiveWorkspace() ?? personal?.id ?? "";
  const current = data.find((w) => w.id === active) ?? personal;

  return (
    <label className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="hidden sm:inline">Workspace</span>
      <select
        aria-label="Workspace"
        className="max-w-[12rem] rounded border border-border bg-card px-2 py-1 text-sm text-foreground"
        value={current?.id ?? ""}
        onChange={(e) => {
          const next = data.find((w) => w.id === e.target.value);
          setActiveWorkspace(next && !next.is_personal ? next.id : null);
          window.location.reload();
        }}
      >
        {data.map((w) => (
          <option key={w.id} value={w.id}>
            {w.brand_name ?? w.name} · {ROLE_LABELS[w.role]}
          </option>
        ))}
      </select>
    </label>
  );
}
