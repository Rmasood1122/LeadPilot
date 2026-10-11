"use client";

import { useState } from "react";
import { createTemplate, updateTemplate } from "@/lib/api/campaigns";
import type { TemplateOut } from "@/lib/api/types";
import {
  hasOptOutInstruction, missingDescriptions, needsOptOutInstruction, placeholderNumbers,
  variableDescriptions,
} from "@/lib/whatsappTemplate";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";

/** Create or edit a WhatsApp template draft. The server requires one
 *  description per {{n}} placeholder (it tells the sequence engine what to
 *  fill in) and, for marketing templates, an opt-out instruction with STOP;
 *  the editor asks for both before it lets you save. */
export function TemplateEditor({ initial, onSave, onClose }: {
  initial?: TemplateOut | null;
  onSave: (t: TemplateOut) => void;
  onClose: () => void;
}) {
  const toast = useToast();
  const [name, setName] = useState(initial?.name ?? "");
  const [body, setBody] = useState(initial?.body ?? "");
  const [descriptions, setDescriptions] = useState<Record<string, string>>(
    initial?.variable_descriptions ?? {},
  );
  const [busy, setBusy] = useState(false);

  const numbers = placeholderNumbers(body);
  const missing = missingDescriptions(body, descriptions);
  const optOut = !needsOptOutInstruction(initial?.category) || hasOptOutInstruction(body);
  const ready = body.trim() !== "" && (Boolean(initial) || name.trim() !== "")
    && missing.length === 0 && optOut;

  async function save() {
    setBusy(true);
    const variable_descriptions = variableDescriptions(body, descriptions);
    try {
      const t = initial
        ? await updateTemplate(initial.id, { body, variable_descriptions })
        : await createTemplate({
            name: name.toLowerCase().replace(/\s+/g, "_"),
            language: "en_US", category: "marketing", body,
            variable_descriptions,
          });
      onSave(t);
      toast("Template saved", "success");
    } catch (err) {
      toast((err as Error).message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {!initial && (
        <div className="space-y-1">
          <Label htmlFor="tname">Name (snake_case)</Label>
          <Input id="tname" value={name} onChange={e => setName(e.target.value)}
                 placeholder="intro_offer" />
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="tbody">Body</Label>
        <Textarea id="tbody" rows={5} value={body}
                  onChange={e => setBody(e.target.value)}
                  placeholder="Hi {{1}}, Sam from LeadPilot. Reply STOP to opt out." />
        <p className="text-xs text-muted-foreground">
          Variables: {"{{1}}"} {"{{2}}"} etc., numbered from 1. Include
          &quot;Reply STOP to opt out.&quot;
        </p>
        {body.trim() !== "" && !optOut && (
          <p role="alert" className="text-xs text-destructive">
            A marketing message must tell the recipient how to opt out, with
            the word STOP in capitals in an instruction, for example
            &quot;Reply STOP to opt out.&quot;
          </p>
        )}
      </div>
      {numbers.map((n) => (
        <div key={n} className="space-y-1">
          <Label htmlFor={`tvar-${n}`}>What goes in {`{{${n}}}`}?</Label>
          <Input id={`tvar-${n}`} value={descriptions[String(n)] ?? ""}
                 onChange={e => setDescriptions(d => ({ ...d, [String(n)]: e.target.value }))}
                 placeholder={n === 1 ? "first name" : "e.g. their company's main problem"} />
        </div>
      ))}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose}>Cancel</Button>
        <Button onClick={save} disabled={busy || !ready}>
          {busy ? "Saving…" : "Save draft"}
        </Button>
      </div>
    </div>
  );
}
