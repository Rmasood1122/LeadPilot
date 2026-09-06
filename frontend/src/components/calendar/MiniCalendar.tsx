"use client";

/** Month picker. Custom-built — no calendar library, per the brief.
 *
 *  A `role="grid"` of buttons rather than a table of divs, because a month
 *  picker IS a two-dimensional structure and a screen reader should be able to
 *  say "week 3, Thursday" rather than reading forty-two unrelated buttons.
 *  Arrow keys move by day and week for the same reason.
 */

import { useMemo, useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";

import {
  DAY_LABELS,
  MONTH_LABELS,
  addDays,
  addMonths,
  dateKey,
  isSameDay,
  isSameMonth,
  monthMatrix,
} from "@/lib/calendar/grid";
import { cn } from "@/lib/utils";

export function MiniCalendar({
  month,
  selected,
  onMonthChange,
  onSelect,
  markedDates,
  minDate,
}: {
  /** Any date in the month being shown. */
  month: Date;
  selected: Date;
  onMonthChange: (next: Date) => void;
  onSelect: (day: Date) => void;
  /** Date keys ("YYYY-MM-DD") to mark with a dot — bookings, or the days a
   *  booking page has slots on. */
  markedDates?: Set<string>;
  /** Days before this are not selectable. The public booking page passes
   *  today; the in-app calendar passes nothing, because looking back at last
   *  month's calls is a normal thing to want. */
  minDate?: Date;
}) {
  const weeks = useMemo(() => monthMatrix(month), [month]);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const today = useMemo(() => new Date(), []);

  const isDisabled = (day: Date) =>
    !!minDate && day.getTime() < new Date(minDate).setHours(0, 0, 0, 0);

  const onKeyDown = (event: React.KeyboardEvent, day: Date) => {
    const moves: Record<string, number> = {
      ArrowLeft: -1,
      ArrowRight: 1,
      ArrowUp: -7,
      ArrowDown: 7,
    };
    const delta = moves[event.key];
    if (delta === undefined) return;
    event.preventDefault();
    const next = addDays(day, delta);
    // Moving off the edge of the visible month pages the picker, rather than
    // trapping the cursor on the 1st or the 31st.
    if (!isSameMonth(next, month)) onMonthChange(next);
    onSelect(next);
    // The button for `next` may not exist yet on a month change; focus is
    // restored by the effect-free `autoFocus`-equivalent below on re-render.
    requestAnimationFrame(() => {
      gridRef.current
        ?.querySelector<HTMLButtonElement>(`[data-day="${dateKey(next)}"]`)
        ?.focus();
    });
  };

  return (
    <div className="select-none">
      <div className="mb-2 flex items-center justify-between">
        <button
          type="button"
          onClick={() => onMonthChange(addMonths(month, -1))}
          aria-label="Previous month"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <ChevronLeft size={16} aria-hidden="true" />
        </button>
        <p className="text-sm font-medium" aria-live="polite">
          {MONTH_LABELS[month.getMonth()]} {month.getFullYear()}
        </p>
        <button
          type="button"
          onClick={() => onMonthChange(addMonths(month, 1))}
          aria-label="Next month"
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
        >
          <ChevronRight size={16} aria-hidden="true" />
        </button>
      </div>

      <div ref={gridRef} role="grid" aria-label="Month">
        <div role="row" className="grid grid-cols-7">
          {DAY_LABELS.map((label) => (
            <div
              key={label}
              role="columnheader"
              // The visible label is one letter to fit; the full name is what
              // a screen reader announces.
              aria-label={label}
              className="pb-1 text-center text-[10px] font-medium uppercase text-muted-foreground"
            >
              {label[0]}
            </div>
          ))}
        </div>

        {weeks.map((week, index) => (
          <div role="row" key={index} className="grid grid-cols-7">
            {week.map((day) => {
              const key = dateKey(day);
              const outside = !isSameMonth(day, month);
              const disabled = isDisabled(day);
              const isSelected = isSameDay(day, selected);
              // aria-selected belongs on the GRIDCELL, not on the button:
              // that is the ARIA date-picker pattern, and role=button does
              // not support the attribute at all (a11y lint catches it, and
              // a screen reader ignores it). aria-current stays on the
              // button, where it means "today" rather than "chosen".
              return (
                <div
                  role="gridcell"
                  key={key}
                  aria-selected={isSelected}
                  className="p-[1px]"
                >
                  <button
                    type="button"
                    data-day={key}
                    disabled={disabled}
                    onClick={() => onSelect(day)}
                    onKeyDown={(event) => onKeyDown(event, day)}
                    aria-current={isSameDay(day, today) ? "date" : undefined}
                    aria-label={day.toDateString()}
                    className={cn(
                      "relative flex h-7 w-full items-center justify-center rounded text-xs",
                      outside && "text-muted-foreground/50",
                      disabled && "cursor-not-allowed opacity-40",
                      !disabled && !isSelected && "hover:bg-muted",
                      isSelected &&
                        "bg-[rgb(var(--primary))] font-semibold text-primary-foreground",
                      isSameDay(day, today) &&
                        !isSelected &&
                        "ring-1 ring-inset ring-[rgb(var(--accent))]",
                    )}
                  >
                    {day.getDate()}
                    {markedDates?.has(key) && !isSelected && (
                      <span
                        aria-hidden="true"
                        className="absolute bottom-0.5 h-1 w-1 rounded-full bg-[rgb(var(--accent))]"
                      />
                    )}
                  </button>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
