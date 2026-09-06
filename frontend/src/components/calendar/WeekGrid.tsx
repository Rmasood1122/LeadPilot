"use client";

/** The week view: Mon–Sun, 7am–10pm, one row per hour. Custom-built.
 *
 * NO CALENDAR LIBRARY, per the brief. The whole thing is a CSS grid of hour
 * cells with bookings absolutely positioned over each day column, and the
 * arithmetic for that lives in src/lib/calendar/grid.ts where it can be tested
 * without a DOM.
 *
 * WHY BOOKINGS ARE ABSOLUTELY POSITIONED AND NOT PLACED IN GRID CELLS
 * A booking is not an hour. A 30-minute call at 10:30 spans half of one cell
 * and half of the next; a 45-minute one spans three quarters of two. Snapping
 * either into a cell would draw them as an hour, and the user would read the
 * grid as saying something it does not.
 *
 * OVERLAPPING BOOKINGS share the column's width rather than covering each
 * other. Two calls at the same time is a state the calendar must be able to
 * SHOW — it is exactly the state the user needs to see and fix — so hiding one
 * behind the other would be the worst possible rendering of it.
 */

import { useMemo } from "react";

import type { Booking } from "@/lib/api/calendar";
import {
  DAY_LABELS,
  GRID_START_HOUR,
  HOUR_HEIGHT,
  blockGeometry,
  dateKey,
  formatHour,
  formatTime,
  gridHours,
  groupByDay,
  isSameDay,
  weekDays,
} from "@/lib/calendar/grid";
import { cn } from "@/lib/utils";

const TONE_BY_STATUS: Record<string, string> = {
  confirmed: "bg-[rgb(var(--primary))]/85 text-primary-foreground",
  pending: "bg-[rgb(var(--warning))]/85 text-white",
  cancelled:
    "bg-muted text-muted-foreground line-through border border-dashed border-border",
  no_show: "bg-[rgb(var(--destructive))]/75 text-white",
};

export function WeekGrid({
  anchor,
  bookings,
  onSelectBooking,
  onSelectSlot,
}: {
  /** Any date in the week to show. */
  anchor: Date;
  bookings: Booking[];
  onSelectBooking: (booking: Booking) => void;
  /** Clicking empty space: opens the "New availability block" modal for that
   *  day and hour. */
  onSelectSlot: (day: Date, hour: number) => void;
}) {
  const days = useMemo(() => weekDays(anchor), [anchor]);
  const hours = useMemo(() => gridHours(), []);
  const byDay = useMemo(() => groupByDay(bookings), [bookings]);
  const today = useMemo(() => new Date(), []);

  return (
    <div className="overflow-x-auto rounded border border-border bg-card">
      {/* min-w keeps the seven columns legible on a phone; the container
          scrolls horizontally rather than crushing them to 40px. */}
      <div className="min-w-[720px]">
        {/* Header row */}
        <div className="sticky top-0 z-10 grid grid-cols-[56px_repeat(7,1fr)] border-b border-border bg-muted/60 backdrop-blur">
          <div aria-hidden="true" />
          {days.map((day, index) => (
            <div
              key={dateKey(day)}
              className={cn(
                "border-l border-border/60 px-2 py-1 text-center text-xs",
                isSameDay(day, today) && "font-semibold text-foreground",
              )}
            >
              <div className="text-muted-foreground">{DAY_LABELS[index]}</div>
              <div
                className={cn(
                  "mx-auto mt-0.5 flex h-6 w-6 items-center justify-center rounded-full",
                  isSameDay(day, today) &&
                    "bg-[rgb(var(--primary))] text-primary-foreground",
                )}
              >
                {day.getDate()}
              </div>
            </div>
          ))}
        </div>

        {/* Body */}
        <div className="relative grid grid-cols-[56px_repeat(7,1fr)]">
          {/* Hour labels */}
          <div>
            {hours.map((hour) => (
              <div
                key={hour}
                style={{ height: HOUR_HEIGHT }}
                className="relative border-b border-border/40 pr-2 text-right text-[10px] text-muted-foreground"
              >
                {/* Nudged up so the label sits ON the line it marks rather
                    than in the middle of the hour it starts. */}
                <span className="absolute -top-1.5 right-2">
                  {formatHour(hour)}
                </span>
              </div>
            ))}
          </div>

          {days.map((day) => {
            const dayBookings = byDay[dateKey(day)] ?? [];
            return (
              <div key={dateKey(day)} className="relative border-l border-border/60">
                {hours.map((hour) => (
                  <button
                    key={hour}
                    type="button"
                    onClick={() => onSelectSlot(day, hour)}
                    aria-label={`Add availability on ${day.toDateString()} at ${formatHour(hour)}`}
                    style={{ height: HOUR_HEIGHT }}
                    className="block w-full border-b border-border/40 transition-colors hover:bg-[rgb(var(--accent))]/10 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-accent"
                  />
                ))}

                {dayBookings.map((booking, index) => (
                  <BookingBlock
                    key={booking.id}
                    booking={booking}
                    lane={laneOf(booking, dayBookings)}
                    lanes={laneCount(dayBookings)}
                    onSelect={onSelectBooking}
                    fallbackIndex={index}
                  />
                ))}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

/** Which horizontal lane a booking occupies among the ones it overlaps.
 *
 *  Deliberately naive: bookings are laid out in start order and each takes the
 *  first lane not already used by something it overlaps. A proper interval
 *  graph colouring would pack them tighter, and for a calendar that rarely has
 *  more than two concurrent items the extra code buys nothing.
 */
function laneOf(booking: Booking, all: Booking[]): number {
  const ordered = [...all].sort(
    (a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
  );
  const lanes: Booking[][] = [];
  for (const candidate of ordered) {
    let placed = -1;
    for (let lane = 0; lane < lanes.length; lane += 1) {
      if (!lanes[lane].some((other) => overlaps(other, candidate))) {
        lanes[lane].push(candidate);
        placed = lane;
        break;
      }
    }
    if (placed === -1) {
      lanes.push([candidate]);
      placed = lanes.length - 1;
    }
    if (candidate.id === booking.id) return placed;
  }
  return 0;
}

function laneCount(all: Booking[]): number {
  let max = 1;
  for (const booking of all) max = Math.max(max, laneOf(booking, all) + 1);
  return max;
}

function overlaps(a: Booking, b: Booking): boolean {
  return (
    new Date(a.start_at) < new Date(b.end_at) &&
    new Date(a.end_at) > new Date(b.start_at)
  );
}

function BookingBlock({
  booking,
  lane,
  lanes,
  onSelect,
  fallbackIndex,
}: {
  booking: Booking;
  lane: number;
  lanes: number;
  onSelect: (booking: Booking) => void;
  fallbackIndex: number;
}) {
  const start = new Date(booking.start_at);
  const end = new Date(booking.end_at);
  const { top, height, clipped } = blockGeometry(start, end);
  const width = 100 / Math.max(1, lanes);

  return (
    <button
      type="button"
      onClick={() => onSelect(booking)}
      title={`${booking.invitee_name} — ${formatTime(start)}`}
      aria-label={`${booking.invitee_name}, ${formatTime(start)} to ${formatTime(end)}, ${booking.status.replace(/_/g, " ")}`}
      style={{
        top,
        height,
        left: `${lane * width}%`,
        width: `calc(${width}% - 2px)`,
        // Later blocks sit above earlier ones so a short call inside a long
        // one is still clickable.
        zIndex: 2 + fallbackIndex,
      }}
      className={cn(
        "absolute overflow-hidden rounded px-1 py-0.5 text-left text-[10px] leading-tight shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
        TONE_BY_STATUS[booking.status] ?? TONE_BY_STATUS.confirmed,
      )}
    >
      <span className="block truncate font-medium">{booking.invitee_name}</span>
      {height > 24 && (
        <span className="block truncate opacity-80">{formatTime(start)}</span>
      )}
      {clipped && (
        <span aria-hidden="true" className="block text-[9px] opacity-70">
          …
        </span>
      )}
    </button>
  );
}
