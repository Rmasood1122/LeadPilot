"use client";

/** Pick a time on a public booking page. Custom-built — no library.
 *
 * The slots come from the server already resolved against the host's
 * availability, their existing bookings and the page's per-day cap; this
 * component's whole job is to group them by the VISITOR's local date and
 * render them as buttons. It deliberately computes nothing about availability
 * itself: a browser that decided which slots were free would disagree with the
 * server the moment somebody else booked one.
 */

import { useMemo } from "react";

import type { Slot } from "@/lib/api/calendar";
import { cn } from "@/lib/utils";

export function SlotPicker({
  slots,
  selectedDate,
  selectedSlot,
  onSelect,
  timezone,
  isLoading,
}: {
  slots: Slot[];
  /** "YYYY-MM-DD" in the visitor's zone. */
  selectedDate: string;
  selectedSlot: Slot | null;
  onSelect: (slot: Slot) => void;
  timezone: string;
  isLoading: boolean;
}) {
  const forDay = useMemo(
    () => slots.filter((slot) => slot.date === selectedDate),
    [slots, selectedDate],
  );

  if (isLoading) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        Loading times…
      </p>
    );
  }

  if (forDay.length === 0) {
    return (
      <p className="rounded border border-dashed border-border p-6 text-center text-sm text-muted-foreground">
        No times available on this day. Try another date.
      </p>
    );
  }

  return (
    <div>
      <p className="mb-2 text-xs text-muted-foreground">
        Times shown in <strong>{timezone}</strong>
      </p>
      <ul
        // A list, not a radiogroup: each entry is an action that advances to
        // the form, not a value being toggled. `aria-current` marks the chosen
        // one for the case where the user comes back to change it.
        className="grid max-h-[320px] grid-cols-2 gap-2 overflow-y-auto pr-1 sm:grid-cols-3"
      >
        {forDay.map((slot) => {
          const start = new Date(slot.start_at);
          const isSelected = selectedSlot?.start_at === slot.start_at;
          return (
            <li key={slot.start_at}>
              <button
                type="button"
                onClick={() => onSelect(slot)}
                aria-current={isSelected ? "true" : undefined}
                className={cn(
                  "w-full rounded border px-3 py-2 text-sm tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
                  isSelected
                    ? "border-transparent bg-[rgb(var(--primary))] font-medium text-primary-foreground"
                    : "border-border hover:border-[rgb(var(--primary))] hover:bg-muted",
                )}
              >
                {start.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
