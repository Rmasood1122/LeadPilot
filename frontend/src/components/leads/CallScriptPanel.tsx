"use client";

/** Part 2 — the call script and the pre-meeting checklist.
 *
 *  The script is EDITABLE, which is the whole point: it is seeded from the
 *  brief and then belongs to the seller. Until they touch it, it is labelled
 *  "suggested" — generated text should never be mistaken for something a
 *  person approved.
 *
 *  The checklist is derived server-side and shown beside it, because the two
 *  answer the same question from different ends: what am I taking into this
 *  call, and what is still missing. */

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ClipboardList, Plus, Save, X } from "lucide-react";

import {
  getReadiness,
  getScript,
  saveScript,
  setPracticeRequired,
} from "@/lib/api/practice";
import {
  emptyScript,
  isSuggested,
  readinessTone,
  scriptGaps,
  scriptSummary,
  sortedItems,
  type CallScript,
} from "@/lib/practice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function CallScriptPanel({ briefId }: { briefId: string }) {
  const toast = useToast();
  const qc = useQueryClient();
  const [draft, setDraft] = useState<CallScript>(emptyScript());

  const script = useQuery({
    queryKey: ["call-script", briefId],
    queryFn: () => getScript(briefId),
  });
  const readiness = useQuery({
    queryKey: ["readiness", briefId],
    queryFn: () => getReadiness(briefId),
  });

  // Seed the editor once, from the server's copy. Deliberately keyed on the
  // brief so switching prospects does not carry another one's words across.
  useEffect(() => {
    if (script.data) setDraft(script.data.script);
  }, [script.data, briefId]);

  const save = useMutation({
    mutationFn: () => saveScript(briefId, draft),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["call-script", briefId] });
      qc.invalidateQueries({ queryKey: ["readiness", briefId] });
      toast("Script saved", "success");
    },
    onError: (e) => toast((e as Error).message, "error"),
  });
  const requirePractice = useMutation({
    mutationFn: (required: boolean) => setPracticeRequired(briefId, required),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["readiness", briefId] });
    },
    onError: (e) => toast((e as Error).message, "error"),
  });

  const gaps = scriptGaps(draft);

  return (
    <div className="space-y-4">
      <Card aria-label="Pre-meeting checklist">
        <CardHeader className="gap-1">
          <CardTitle className="flex items-center gap-2 text-sm">
            <ClipboardList size={16} aria-hidden="true" /> Before this call
          </CardTitle>
          {readiness.data && (
            <p className="text-xs text-muted-foreground">
              {readiness.data.headline}
            </p>
          )}
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <AsyncState isLoading={readiness.isLoading} error={readiness.error}>
            {readiness.data && (
              <>
                <ul className="space-y-1">
                  {sortedItems(readiness.data).map((item) => (
                    <li key={item.key} className="flex flex-wrap items-baseline gap-2">
                      {item.done
                        ? <Check size={14} aria-hidden="true" />
                        : <X size={14} aria-hidden="true" />}
                      <span className={item.done ? "" : "font-medium"}>{item.label}</span>
                      {item.blocking && <Badge tone="destructive">Blocking</Badge>}
                      <span className="text-xs text-muted-foreground">{item.detail}</span>
                    </li>
                  ))}
                </ul>
                <Badge tone={readinessTone(readiness.data)}>
                  {readiness.data.done} of {readiness.data.total} done
                </Badge>
                <div>
                  <Button size="sm" variant="ghost"
                          disabled={requirePractice.isPending}
                          onClick={() =>
                            requirePractice.mutate(!readiness.data!.practice_required)}>
                    {readiness.data.practice_required
                      ? "Practice is required for this call — make it optional"
                      : "Require a rehearsal before this call"}
                  </Button>
                </div>
              </>
            )}
          </AsyncState>
        </CardContent>
      </Card>

      <Card aria-label="Call script">
        <CardHeader className="flex-row items-start justify-between gap-2">
          <div>
            <CardTitle className="text-sm">Your call script</CardTitle>
            <p className="text-xs text-muted-foreground">{scriptSummary(draft)}</p>
          </div>
          <div className="flex items-center gap-2">
            {isSuggested(script.data) && <Badge tone="warning">Suggested</Badge>}
            <Button size="sm" disabled={save.isPending} onClick={() => save.mutate()}>
              <Save size={14} aria-hidden="true" />
              {save.isPending ? "Saving…" : "Save"}
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <AsyncState isLoading={script.isLoading} error={script.error}>
            {isSuggested(script.data) && (
              <p className="text-xs text-muted-foreground">
                This is the suggested draft from the brief. Edit it so it sounds
                like you — nothing here is fixed.
              </p>
            )}

            <div>
              <Label htmlFor="script-opening">Opening (first 60 seconds)</Label>
              <Textarea id="script-opening" rows={3} value={draft.opening}
                        onChange={(e) => setDraft({ ...draft, opening: e.target.value })} />
            </div>

            <fieldset className="space-y-2">
              <legend className="text-xs font-medium text-muted-foreground">
                Discovery questions
              </legend>
              {draft.discovery.map((question, index) => (
                <div key={index} className="flex gap-2">
                  <Input value={question} aria-label={`Discovery question ${index + 1}`}
                         onChange={(e) => {
                           const next = [...draft.discovery];
                           next[index] = e.target.value;
                           setDraft({ ...draft, discovery: next });
                         }} />
                  <Button size="sm" variant="ghost" aria-label="Remove this question"
                          onClick={() => setDraft({
                            ...draft,
                            discovery: draft.discovery.filter((_, i) => i !== index),
                          })}>
                    <X size={14} aria-hidden="true" />
                  </Button>
                </div>
              ))}
              <Button size="sm" variant="ghost"
                      onClick={() => setDraft({ ...draft,
                                                discovery: [...draft.discovery, ""] })}>
                <Plus size={14} aria-hidden="true" /> Add a question
              </Button>
            </fieldset>

            <fieldset className="space-y-2">
              <legend className="text-xs font-medium text-muted-foreground">
                If they say…
              </legend>
              {draft.objections.map((item, index) => (
                <div key={index} className="space-y-1 border-l-2 border-border pl-2">
                  <Input value={item.objection} aria-label={`Objection ${index + 1}`}
                         onChange={(e) => {
                           const next = [...draft.objections];
                           next[index] = { ...item, objection: e.target.value };
                           setDraft({ ...draft, objections: next });
                         }} />
                  <Textarea rows={2} value={item.response}
                            aria-label={`Response ${index + 1}`}
                            onChange={(e) => {
                              const next = [...draft.objections];
                              next[index] = { ...item, response: e.target.value };
                              setDraft({ ...draft, objections: next });
                            }} />
                </div>
              ))}
              <Button size="sm" variant="ghost"
                      onClick={() => setDraft({
                        ...draft,
                        objections: [...draft.objections, { objection: "", response: "" }],
                      })}>
                <Plus size={14} aria-hidden="true" /> Add an objection
              </Button>
            </fieldset>

            <div>
              <Label htmlFor="script-close">Close</Label>
              <Textarea id="script-close" rows={2} value={draft.close}
                        onChange={(e) => setDraft({ ...draft, close: e.target.value })} />
            </div>

            <div>
              <Label htmlFor="script-notes">Notes to yourself</Label>
              <Textarea id="script-notes" rows={2} value={draft.notes}
                        onChange={(e) => setDraft({ ...draft, notes: e.target.value })} />
            </div>

            {gaps.length > 0 && (
              <p className="text-xs text-muted-foreground">
                Still blank: {gaps.join(", ")}.
              </p>
            )}
          </AsyncState>
        </CardContent>
      </Card>
    </div>
  );
}
