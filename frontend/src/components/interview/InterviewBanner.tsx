"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getInterviewStatus, snoozeInterview } from "@/lib/api/interview";
import { SNOOZE_DAYS } from "@/lib/interview";

/** Once a month: ask the user to do the style interview. Never blocks the app. */
export function InterviewBanner() {
  const path = usePathname();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["interview-status"], queryFn: getInterviewStatus,
                            staleTime: 5 * 60 * 1000, retry: false });
  const later = useMutation({
    mutationFn: () => snoozeInterview(SNOOZE_DAYS),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["interview-status"] }),
  });
  if (!status.data?.due || path.startsWith("/interview")) return null;
  return (
    <div role="status" className="mb-4 flex flex-wrap items-center gap-3 rounded border border-border bg-card p-3 text-sm">
      <span>
        Time for your monthly voice interview (about 5 minutes). It teaches LeadPilot to write
        your messages the way you speak.
      </span>
      <Link href="/interview" className="rounded bg-primary px-3 py-1 text-primary-foreground">Start</Link>
      <button className="underline" disabled={later.isPending} onClick={() => later.mutate()}>
        Remind me in {SNOOZE_DAYS} days
      </button>
    </div>
  );
}
