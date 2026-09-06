"use client";

/** The action items from a meeting, as a saveable checkbox list.
 *
 * OPTIMISTIC, WITH A DEBOUNCED SAVE. Ticking a box has to feel instant — the
 * user is going down a list — so the checkbox flips locally and the whole list
 * is PUT half a second later. Ticking five items in a row therefore costs one
 * request rather than five, and the last write wins because the payload is
 * always the complete list.
 *
 * WHY THE WHOLE LIST AND NOT A PER-ITEM PATCH: items have no stable id (see
 * calendar_tasks._merge_action_items for why generating one would not survive
 * a regenerated summary), and the list is what the user perceives as one
 * thing.
 */

import { useEffect, useRef, useState } from "react";
import { Plus, Trash2 } from "lucide-react";

import type { ActionItem } from "@/lib/api/meetings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const SAVE_DEBOUNCE_MS = 500;

export function ActionItemsList({
  items,
  onSave,
  readOnly,
}: {
  items: ActionItem[];
  onSave: (items: ActionItem[]) => void;
  readOnly?: boolean;
}) {
  const [local, setLocal] = useState<ActionItem[]>(items);
  const [draft, setDraft] = useState("");
  const timer = useRef<number | null>(null);
  // Tracks whether the user has edited, so a refetch landing with server data
  // does not overwrite a tick made half a second ago.
  const dirty = useRef(false);

  useEffect(() => {
    if (dirty.current) return;
    setLocal(items);
  }, [items]);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const commit = (next: ActionItem[]) => {
    dirty.current = true;
    setLocal(next);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      dirty.current = false;
      onSave(next);
    }, SAVE_DEBOUNCE_MS);
  };

  const toggle = (index: number) =>
    commit(
      local.map((item, i) =>
        i === index ? { ...item, done: !item.done } : item,
      ),
    );

  const remove = (index: number) =>
    commit(local.filter((_, i) => i !== index));

  const add = () => {
    const text = draft.trim();
    if (!text) return;
    commit([...local, { text, owner: "us", due: null, done: false }]);
    setDraft("");
  };

  return (
    <div className="space-y-2">
      {local.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No action items. Nothing was committed to on this call — or the
          summary has not run yet.
        </p>
      ) : (
        <ul className="space-y-1">
          {local.map((item, index) => (
            <li
              key={`${item.text}-${index}`}
              className="flex items-start gap-2 rounded border border-border px-2 py-1.5 text-sm"
            >
              <input
                type="checkbox"
                checked={!!item.done}
                disabled={readOnly}
                onChange={() => toggle(index)}
                aria-label={item.text}
                className="mt-0.5 h-4 w-4 shrink-0 accent-[rgb(var(--primary))]"
              />
              <span
                className={cn(
                  "min-w-0 flex-1 break-words",
                  item.done && "text-muted-foreground line-through",
                )}
              >
                {item.text}
                {item.due && (
                  <span className="ml-2 text-xs text-muted-foreground">
                    due {item.due}
                  </span>
                )}
              </span>
              <Badge
                tone={item.owner === "us" ? "primary" : "default"}
                className="shrink-0"
              >
                {item.owner === "us" ? "you" : "client"}
              </Badge>
              {!readOnly && (
                <button
                  type="button"
                  onClick={() => remove(index)}
                  aria-label={`Remove: ${item.text}`}
                  className="shrink-0 text-muted-foreground hover:text-[rgb(var(--destructive))]"
                >
                  <Trash2 size={14} aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {!readOnly && (
        <div className="flex gap-2">
          <Input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                add();
              }
            }}
            placeholder="Add an action item"
            aria-label="New action item"
          />
          <Button size="sm" variant="outline" onClick={add} disabled={!draft.trim()}>
            <Plus size={14} aria-hidden="true" />
            Add
          </Button>
        </div>
      )}
    </div>
  );
}
