"use client";

/** Feature 3: send a recording bot to the call, and say where its transcript is.
 *
 *  The summary never waits on this. Ending the meeting summarises the notes
 *  straight away; a transcript that arrives later upgrades the summary. So the
 *  copy here describes the transcript's state, not a blocking progress bar. */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Mic } from "lucide-react";

import {
  startRecordingBot,
  type MeetingDetail,
  type TranscriptStatus,
} from "@/lib/api/meetings";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";

const STATUS_COPY: Record<TranscriptStatus, string> = {
  requesting: "Starting the recording bot…",
  pending: "Recording bot scheduled. The transcript arrives after the call.",
  received: "Transcript received — the summary uses it.",
  failed: "The transcript could not be produced. The summary uses your notes.",
  timed_out: "No transcript yet. The summary uses your notes and updates if it arrives.",
};

export function RecordingControl({ meeting }: { meeting: MeetingDetail }) {
  const toast = useToast();
  const [status, setStatus] = useState<TranscriptStatus | null>(meeting.transcript_status);

  const start = useMutation({
    mutationFn: () => startRecordingBot(meeting.id),
    onSuccess: (res) => {
      setStatus(res.transcript_status);
      toast("Recording bot scheduled", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const current = status ?? meeting.transcript_status;
  const over = meeting.status === "completed" || meeting.status === "cancelled";

  if (current) {
    return <p className="text-xs text-muted-foreground">{STATUS_COPY[current]}</p>;
  }
  if (over) return null;
  return (
    <div className="space-y-1">
      <Button
        variant="outline"
        disabled={start.isPending || !meeting.meeting_url}
        onClick={() => start.mutate()}
      >
        <Mic size={16} aria-hidden="true" />
        Record &amp; transcribe
      </Button>
      <p className="text-xs text-muted-foreground">
        {meeting.meeting_url
          ? "A bot joins the call and records it. Tell everyone on the call that it is being recorded."
          : "Add a join link to send a recording bot."}
      </p>
    </div>
  );
}
