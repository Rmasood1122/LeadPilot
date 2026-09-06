/** Calendar geometry and date maths — pure functions, no React, no library.
 *
 * NO CALENDAR LIBRARY. Not FullCalendar, not react-big-calendar, not date-fns.
 * The brief forbids the first two and the third would be a dependency carrying
 * two hundred functions to do what the twelve below do — every one of which is
 * a few lines of `Date` arithmetic that the platform already implements.
 *
 * Kept as pure functions over plain `Date`s so the awkward parts (a week that
 * crosses a month boundary, a booking that starts before the grid's first hour,
 * a month whose first day is a Sunday) can be unit-tested without mounting a
 * component.
 *
 * WEEK STARTS MONDAY, and `dayOfWeek` is 0=Monday..6=Sunday throughout — the
 * same convention as `datetime.weekday()` on the backend, so an availability
 * rule means the same thing on both sides. JavaScript's own `getDay()` is
 * 0=Sunday, which is why `weekdayIndex` exists and why nothing here calls
 * `getDay()` directly.
 */

/** First hour shown in the week grid (7am), per the brief. */
export const GRID_START_HOUR = 7;
/** Last hour shown, exclusive of its own row (so the grid ends at 10pm). */
export const GRID_END_HOUR = 22;
/** Pixel height of one hour row. The one number that ties the CSS grid and
 *  the absolute positioning of booking blocks together. */
export const HOUR_HEIGHT = 48;

export const DAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const MONTH_LABELS = [
  "January", "February", "March", "April", "May", "June",
  "July", "August", "September", "October", "November", "December",
];

/** 0 = Monday .. 6 = Sunday. See the module docstring. */
export function weekdayIndex(date: Date): number {
  return (date.getDay() + 6) % 7;
}

export function startOfDay(date: Date): Date {
  const out = new Date(date);
  out.setHours(0, 0, 0, 0);
  return out;
}

export function addDays(date: Date, days: number): Date {
  const out = new Date(date);
  // setDate, not "+ days * 86_400_000": adding milliseconds across a DST
  // boundary lands an hour off, and this is used to walk a week that may
  // contain one.
  out.setDate(out.getDate() + days);
  return out;
}

export function addMonths(date: Date, months: number): Date {
  const out = new Date(date);
  // Day 1 first: setMonth on the 31st of a month rolls into the next one
  // (31 March + 1 month = 1 May), so a "next month" button would skip April.
  out.setDate(1);
  out.setMonth(out.getMonth() + months);
  return out;
}

/** The Monday of `date`'s week, at 00:00 local. */
export function startOfWeek(date: Date): Date {
  return addDays(startOfDay(date), -weekdayIndex(date));
}

/** The seven days of `date`'s week, Monday first. */
export function weekDays(date: Date): Date[] {
  const monday = startOfWeek(date);
  return Array.from({ length: 7 }, (_, i) => addDays(monday, i));
}

/** The hours the week grid renders, as row labels. */
export function gridHours(): number[] {
  return Array.from(
    { length: GRID_END_HOUR - GRID_START_HOUR },
    (_, i) => GRID_START_HOUR + i,
  );
}

/** A six-row month grid, Monday-first, padded with the neighbouring months.
 *
 *  Always six rows, never five: a month picker whose height changes as you
 *  page through the year makes the whole sidebar jump, and the fix costs one
 *  mostly-grey row.
 */
export function monthMatrix(date: Date): Date[][] {
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const gridStart = startOfWeek(first);
  return Array.from({ length: 6 }, (_, week) =>
    Array.from({ length: 7 }, (_, day) => addDays(gridStart, week * 7 + day)),
  );
}

export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  );
}

export function isSameMonth(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth();
}

/** "YYYY-MM-DD" in LOCAL time.
 *
 *  Deliberately not `toISOString().slice(0, 10)`, which converts to UTC first
 *  and therefore files a 23:30 booking under tomorrow for anyone east of
 *  Greenwich — the single most common date bug in a calendar UI. */
export function dateKey(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export function formatHour(hour: number): string {
  const suffix = hour < 12 ? "am" : "pm";
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}${suffix}`;
}

export function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export interface BlockGeometry {
  /** Pixels from the top of the day column. */
  top: number;
  /** Pixel height. Never less than one, so a 15-minute booking is visible. */
  height: number;
  /** True when the event extends above or below the rendered hours, so the
   *  block can say so instead of silently appearing to be shorter than it is. */
  clipped: boolean;
}

/** Where a booking sits in a day column.
 *
 *  Clamped to the rendered window rather than allowed to overflow: an event at
 *  06:00 would otherwise be drawn at a negative offset, escape the column and
 *  overlap the header. `clipped` is returned so the caller can mark it.
 */
export function blockGeometry(start: Date, end: Date): BlockGeometry {
  const startHours = start.getHours() + start.getMinutes() / 60;
  const endHours = end.getHours() + end.getMinutes() / 60;
  // An end of exactly midnight belongs to the END of this day, not its start.
  const normalisedEnd = endHours <= startHours ? GRID_END_HOUR : endHours;

  const clampedStart = Math.max(startHours, GRID_START_HOUR);
  const clampedEnd = Math.min(normalisedEnd, GRID_END_HOUR);
  const clipped = startHours < GRID_START_HOUR || normalisedEnd > GRID_END_HOUR;

  return {
    top: (clampedStart - GRID_START_HOUR) * HOUR_HEIGHT,
    height: Math.max(1, (clampedEnd - clampedStart) * HOUR_HEIGHT),
    clipped,
  };
}

/** Group anything with a `start_at` by its LOCAL date key. */
export function groupByDay<T extends { start_at: string }>(
  items: T[],
): Record<string, T[]> {
  const out: Record<string, T[]> = {};
  for (const item of items) {
    const key = dateKey(new Date(item.start_at));
    (out[key] ??= []).push(item);
  }
  return out;
}

/** The browser's IANA zone, with a fallback that never throws.
 *
 *  `resolvedOptions().timeZone` is undefined in a handful of older WebViews —
 *  including some the Capacitor build runs in — and an undefined zone sent to
 *  the slots endpoint would come back grouped by UTC dates. */
export function browserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  } catch {
    return "UTC";
  }
}

/** "in 3 days" / "in 2h 15m" / "now" — the countdown on an upcoming meeting.
 *
 *  Returns null once the target is in the past, so the caller renders
 *  something else entirely rather than a negative countdown. */
export function countdown(target: Date, now: Date = new Date()): string | null {
  const ms = target.getTime() - now.getTime();
  if (ms <= 0) return null;
  const minutes = Math.floor(ms / 60_000);
  if (minutes < 1) return "now";
  if (minutes < 60) return `in ${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `in ${hours}h ${minutes % 60}m`;
  const days = Math.floor(hours / 24);
  return `in ${days} day${days === 1 ? "" : "s"}`;
}

/** "01:23:45" — the meeting-room timer. Hours are dropped under an hour. */
export function elapsed(fromMs: number, nowMs: number): string {
  const total = Math.max(0, Math.floor((nowMs - fromMs) / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}
