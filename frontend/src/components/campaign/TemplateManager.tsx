"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  createTemplate,
  generateTemplates,
  submitTemplate,
  syncTemplate,
  updateTemplate,
} from "@/lib/api/campaigns";
import { useTemplates } from "@/lib/api/hooks";
import type { TemplateOut } from "@/lib/api/types";
import { Badge, statusTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Textarea } from "@/components/ui/input";
import { Modal } from "@/components/ui/dialog";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

export function TemplateManager({ strategyId }: { strategyId: string }) {
  const { data, isLoading, error } = useTemplates();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [editing, setEditing] = useState<TemplateOut | null>(null);
  const [creating, setCreating] = useState(false);
  const [generated, setGenerated] = useState<TemplateOut[] | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["wa-templates"] });

  async function run(fn: () => Promise<unknown>, okMsg: string) {
    setBusy(true);
    try {
      await fn();
      toast(okMsg, "success");
      refresh();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Failed", "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle className="text-sm">WhatsApp templates</CardTitle>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" disabled={busy || !strategyId}
                  onClick={() =>
                    run(async () => {
                      const res = await generateTemplates(strategyId);
                      setGenerated(res.templates);
                    }, "Drafts generated — review before submitting")}>
            Generate with AI
          </Button>
          <Button size="sm" onClick={() => setCreating(true)}>New draft</Button>
        </div>
      </CardHeader>
      <CardContent>
        <AsyncState isLoading={isLoading} error={error}
                    empty={!data?.templates.length}
                    emptyLabel="No templates yet. Cold WhatsApp outreach requires a Meta-approved template — create or generate a draft.">
          <ul className="space-y-2">
            {data?.templates.map((t) => (
              <li key={t.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded border border-border p-2 text-sm">
                <div className="min-w-0">
                  <p className="truncate font-medium">
                    {t.name}
                    <span className="ml-1 text-xs text-muted-foreground">
                      {t.language} · v{t.version ?? 1}
                    </span>
                  </p>
                  {t.status === "rejected" && t.rejection_reason && (
                    <p className="text-xs text-destructive">
                      Rejected by Meta: {t.rejection_reason}
                    </p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge tone={statusTone(t.status)}>{t.status}</Badge>
                  {(t.status === "draft" || t.status === "rejected") && (
                    <>
                      <Button size="sm" variant="ghost" onClick={() => setEditing(t)}>
                        Edit
                      </Button>
                      <Button size="sm" variant="outline" disabled={busy}
                              onClick={() =>
                                run(() => submitTemplate(t.id),
                                    "Submitted to Meta — approval can take minutes to days")}>
                        Submit to Meta
                      </Button>
                    </>
                  )}
                  {t.status === "submitted" && (
                    <Button size="sm" variant="ghost" disabled={busy}
                            onClick={() => run(() => syncTemplate(t.id), "Status synced")}>
                      Check status
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        </AsyncState>
        <p className="mt-3 text-xs text-muted-foreground">
          Meta reviews every template; approval can take minutes to days.
          Only approved templates can be sent, and only to leads with a
          recorded opt-in.
        </p>
      </CardContent>

      {(creating || editing) && (
        <TemplateForm
          template={editing}
          busy={busy}
          onClose={() => { setCreating(false); setEditing(null); }}
          onSave={async (values) => {
            await run(async () => {
              if (editing) await updateTemplate(editing.id, values);
              else await createTemplate({ language: "en_US", category: "marketing", ...values });
            }, editing ? "Draft updated" : "Draft created");
            setCreating(false);
            setEditing(null);
          }}
        />
      )}

      {generated && (
        <Modal open onClose={() => setGenerated(null)} title="AI-generated drafts">
          <div className="space-y-3">
            {generated.map((t) => (
              <div key={t.id} className="rounded border border-border p-2 text-sm">
                <p className="font-medium">{t.name}</p>
                <p className="whitespace-pre-wrap text-muted-foreground">{t.body}</p>
              </div>
            ))}
            <p className="text-xs text-muted-foreground">
              Saved as drafts — edit then submit the ones you like.
            </p>
          </div>
        </Modal>
      )}
    </Card>
  );
}

function TemplateForm({
  template,
  busy,
  onClose,
  onSave,
}: {
  template: TemplateOut | null;
  busy: boolean;
  onClose: () => void;
  onSave: (v: { name: string; body: string; variable_descriptions: Record<string, string> }) => void;
}) {
  const [name, setName] = useState(template?.name ?? "");
  const [body, setBody] = useState(template?.body ?? "");
  const variables = Array.from(body.matchAll(/\{\{(\d+)\}\}/g)).map((m) => m[1]);
  const [descriptions, setDescriptions] = useState<Record<string, string>>(
    template?.variable_descriptions ?? {},
  );
  return (
    <Modal open onClose={onClose}
           title={template ? `Edit ${template.name}` : "New template draft"}>
      <div className="space-y-3">
        {!template && (
          <div className="space-y-1">
            <Label htmlFor="tpl-name">Name (lowercase_snake_case)</Label>
            <Input id="tpl-name" value={name}
                   onChange={(e) => setName(e.target.value)} />
          </div>
        )}
        <div className="space-y-1">
          <Label htmlFor="tpl-body">
            Body — use {"{{1}}"}, {"{{2}}"} for variables; include an opt-out line
          </Label>
          <Textarea id="tpl-body" rows={5} value={body}
                    onChange={(e) => setBody(e.target.value)} />
        </div>
        {variables.map((v) => (
          <div key={v} className="space-y-1">
            <Label htmlFor={`var-${v}`}>{"{{" + v + "}}"} means…</Label>
            <Input id={`var-${v}`} value={descriptions[v] ?? ""}
                   placeholder="e.g. first name"
                   onChange={(e) =>
                     setDescriptions((d) => ({ ...d, [v]: e.target.value }))} />
          </div>
        ))}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button disabled={busy || !body || (!template && !name)}
                  onClick={() => onSave({ name, body, variable_descriptions: descriptions })}>
            Save draft
          </Button>
        </div>
      </div>
    </Modal>
  );
}
