"use client";

import { useQuery } from "@tanstack/react-query";
import { countInbox } from "@/lib/api/inbox";

export function inboxBadgeText(count: number): string | null {
  if (count <= 0) return null;
  return count > 99 ? "99+" : String(count);
}

/** Prospects waiting on an answer (GET /inbox/count), next to the Inbox nav
 *  entry. Refreshed every minute; a failed request shows nothing. */
export function InboxBadge() {
  const { data } = useQuery({
    queryKey: ["inbox-count"],
    queryFn: countInbox,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const text = inboxBadgeText(data?.needs_reply ?? 0);
  if (text === null) return null;
  return (
    <span aria-label={`${text} waiting on a reply`}
          className="ml-auto rounded-full bg-destructive px-1.5 text-[10px] font-semibold leading-4 text-white">
      {text}
    </span>
  );
}
