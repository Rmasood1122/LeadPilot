"use client";

/** Part 2 — the mock interview: the AI plays the prospect, you practise.
 *
 *  Three deliberate choices visible here:
 *
 *  The OBJECTIVES are shown before the first line is typed. Practice without a
 *  target is just a conversation, and the seller should know what this run is
 *  supposed to teach them.
 *
 *  A FAILED turn keeps what the seller said. The API saves their line before
 *  the model is asked, so a model outage shows a retry banner rather than
 *  swallowing a sentence someone thought about.
 *
 *  The FEEDBACK leads with the one thing to change. A review that opens with
 *  five compliments is a review nobody acts on. */

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Mic, Send, Square } from "lucide-react";

import {
  finishPractice,
  getPracticeHistory,
  sendPracticeReply,
  startPractice,
} from "@/lib/api/practice";
import {
  DIFFICULTIES,
  canBeScored,
  difficultyNote,
  historyHeadline,
  isNearlyOver,
  scoreRows,
  scoreTone,
  turnBudget,
  type Difficulty,
  type RoleplaySession,
} from "@/lib/practice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label, Textarea } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";

export function RoleplayPanel({ leadId, briefId }: {
  leadId?: string;
  briefId?: string;
}) {
  const toast = useToast();
  const qc = useQueryClient();
  const [difficulty, setDifficulty] = useState<Difficulty>("realistic");
  const [session, setSession] = useState<RoleplaySession | null>(null);
  const [message, setMessage] = useState("");
  const [lastFailed, setLastFailed] = useState(false);

  const history = useQuery({
    queryKey: ["practice-history", leadId ?? ""],
    queryFn: () => getPracticeHistory(leadId),
  });

  const start = useMutation({
    mutationFn: () => startPractice({ lead_id: leadId, brief_id: briefId, difficulty }),
    onSuccess: (data) => { setSession(data); setLastFailed(false); },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const speak = useMutation({
    mutationFn: (text: string) => sendPracticeReply(session!.id, text),
    onSuccess: (result) => {
      setSession(result.session);
      setLastFailed(result.status === "failed");
      if (result.status === "failed") {
        toast("The prospect did not answer — your line was kept, try again", "error");
      }
      if (result.limit_reached) toast("That is the end of the rehearsal", "info");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const finish = useMutation({
    mutationFn: (abandoned: boolean) => finishPractice(session!.id, abandoned),
    onSuccess: (data) => {
      setSession(data);
      qc.invalidateQueries({ queryKey: ["practice-history"] });
      qc.invalidateQueries({ queryKey: ["readiness"] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const active = session?.status === "active";
  const send = () => {
    const text = message.trim();
    if (!text) return;
    setMessage("");
    speak.mutate(text);
  };

  return (
    <div className="space-y-4">
      <Card aria-label="Practice a call">
        <CardHeader className="flex-row items-start justify-between gap-2">
          <div>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Mic size={16} aria-hidden="true" /> Practice this call
            </CardTitle>
            <p className="text-xs text-muted-foreground">
              {historyHeadline(history.data)}
            </p>
          </div>
          {session && <Badge tone="default">{turnBudget(session)}</Badge>}
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {!session && (
            <div className="flex flex-wrap items-end gap-2">
              <div>
                <Label htmlFor="difficulty">How hard should they be?</Label>
                <NativeSelect id="difficulty" className="w-48" value={difficulty}
                              onChange={(e) =>
                                setDifficulty(e.target.value as Difficulty)}>
                  {DIFFICULTIES.map((d) => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </NativeSelect>
              </div>
              <Button disabled={start.isPending} onClick={() => start.mutate()}>
                {start.isPending ? "Setting up…" : "Start the call"}
              </Button>
              <p className="w-full text-xs text-muted-foreground">
                {difficultyNote(difficulty)}
              </p>
            </div>
          )}

          {session && (
            <>
              {session.objectives.length > 0 && (
                <div>
                  <p className="text-xs font-medium text-muted-foreground">
                    What you are practising
                  </p>
                  <ul className="list-disc pl-4 text-xs text-muted-foreground">
                    {session.objectives.map((goal) => <li key={goal}>{goal}</li>)}
                  </ul>
                </div>
              )}

              <ul className="max-h-96 space-y-2 overflow-y-auto" aria-label="Transcript">
                {(session.turns ?? []).map((turn) => (
                  <li key={turn.turn_no}
                      className={cn("rounded p-2",
                                    turn.role === "seller"
                                      ? "bg-[rgb(var(--primary))]/10 ml-8"
                                      : "bg-muted mr-8")}>
                    <p className="text-xs font-medium text-muted-foreground">
                      {turn.role === "seller" ? "You" : session.lead?.full_name ?? "Prospect"}
                    </p>
                    <p className="whitespace-pre-line">{turn.content}</p>
                  </li>
                ))}
              </ul>

              {lastFailed && (
                <p className="flex items-start gap-2 text-xs">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" aria-hidden="true" />
                  The prospect did not answer that one. Your line was kept — say
                  something else, or try again.
                </p>
              )}

              {active && (
                <div className="space-y-2">
                  <Label htmlFor="roleplay-message">Your turn</Label>
                  <Textarea id="roleplay-message" rows={3} value={message}
                            onChange={(e) => setMessage(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) send();
                            }} />
                  <div className="flex flex-wrap gap-2">
                    <Button disabled={!message.trim() || speak.isPending} onClick={send}>
                      <Send size={14} aria-hidden="true" />
                      {speak.isPending ? "…" : "Say it"}
                    </Button>
                    <Button variant="outline" disabled={finish.isPending}
                            onClick={() => finish.mutate(false)}>
                      <Square size={14} aria-hidden="true" />
                      {canBeScored(session) ? "End and get feedback" : "End (too short to score)"}
                    </Button>
                  </div>
                  {isNearlyOver(session) && (
                    <p className="text-xs text-muted-foreground">
                      Nearly at the end of the rehearsal — start closing.
                    </p>
                  )}
                </div>
              )}

              {session.status === "abandoned" && (
                <p className="text-xs text-muted-foreground">
                  Ended early, so this one was not scored.
                </p>
              )}

              {session.status === "completed" && (
                <Feedback session={session} />
              )}

              {!active && (
                <Button variant="ghost" onClick={() => { setSession(null); setMessage(""); }}>
                  Practise again
                </Button>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <AsyncState isLoading={history.isLoading} error={history.error}
                  empty={!history.data?.trend.length} emptyLabel="">
        {history.data && history.data.trend.length > 1 && (
          <Card aria-label="Practice history">
            <CardHeader><CardTitle className="text-sm">Your scores over time</CardTitle></CardHeader>
            <CardContent>
              <ul className="space-y-1 text-sm">
                {history.data.trend.map((point, index) => (
                  <li key={`${point.at}-${index}`} className="flex justify-between gap-2">
                    <span className="text-muted-foreground">
                      {point.at ? new Date(point.at).toLocaleDateString() : "—"}
                    </span>
                    <Badge tone={scoreTone(point.overall)}>{point.overall}</Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        )}
      </AsyncState>
    </div>
  );
}

function Feedback({ session }: { session: RoleplaySession }) {
  const feedback = session.feedback;
  if (!feedback) {
    return (
      <p className="text-xs text-muted-foreground">
        {session.error ?? "No feedback was produced for this session."}
      </p>
    );
  }
  return (
    <div className="space-y-3">
      {/* The one change first: a review that opens with five compliments is a
          review nobody acts on. */}
      {feedback.one_thing && (
        <p className="font-medium">Change one thing: {feedback.one_thing}</p>
      )}

      <div className="flex flex-wrap gap-2">
        {scoreRows(session.scores).map((row) => (
          <Badge key={row.key} tone={scoreTone(row.value)}>
            {row.label} {row.value}
          </Badge>
        ))}
      </div>

      {feedback.objections_missed.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">
            Objections you did not handle
          </p>
          <ul className="list-disc pl-4 text-sm">
            {feedback.objections_missed.map((item) => (
              <li key={item.objection}>
                “{item.objection}” — {item.why}
              </li>
            ))}
          </ul>
        </div>
      )}

      {feedback.improve.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">To improve</p>
          <ul className="list-disc pl-4 text-sm">
            {feedback.improve.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </div>
      )}

      {feedback.went_well.length > 0 && (
        <div>
          <p className="text-xs font-medium text-muted-foreground">What worked</p>
          <ul className="list-disc pl-4 text-sm">
            {feedback.went_well.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </div>
      )}

      {(feedback.tone_notes || feedback.pacing_notes) && (
        <p className="text-xs text-muted-foreground">
          {[feedback.tone_notes, feedback.pacing_notes].filter(Boolean).join(" ")}
        </p>
      )}
    </div>
  );
}
