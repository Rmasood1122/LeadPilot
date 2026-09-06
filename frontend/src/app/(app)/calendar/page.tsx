"use client";

/** Engagement Hub, Feature 2 — the in-app calendar.
 *
 * Left: a month picker and the weekly availability editor.
 * Right: the week grid, with bookings as blocks.
 *
 * Both custom-built (src/components/calendar/*, src/lib/calendar/grid.ts) —
 * no FullCalendar, no react-big-calendar, no date library, per the brief.
 *
 * AVAILABILITY IS EDITED AS A WHOLE WEEK AND SAVED IN ONE PUT. The user drags
 * blocks around, deletes one, adds another, and presses Save; the server
 * replaces the set. Per-block requests would let a partial failure leave a
 * schedule the user never saw, on the one screen whose entire job is to say
 * when they are free.
 */

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link2, Plus, Trash2 } from "lucide-react";

import {
  getAvailability,
  listBookings,
  saveAvailability,
  type AvailabilityBlock,
  type Booking,
} from "@/lib/api/calendar";
import {
  DAY_LABELS,
  addDays,
  browserTimezone,
  dateKey,
  startOfWeek,
  weekDays,
} from "@/lib/calendar/grid";
import { BookingDrawer } from "@/components/calendar/BookingDrawer";
import { MiniCalendar } from "@/components/calendar/MiniCalendar";
import { WeekGrid } from "@/components/calendar/WeekGrid";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Modal } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

/** New blocks default to a working morning in the browser's zone — the
 *  overwhelmingly common case, and a default the user can change in two
 *  keystrokes beats an empty form they must fill in four times. */
const DEFAULT_START = "09:00";
const DEFAULT_END = "17:00";

export default function CalendarPage() {
  const toast = useToast();
  const queryClient = useQueryClient();

  const [anchor, setAnchor] = useState(() => new Date());
  const [month, setMonth] = useState(() => new Date());
  const [openBooking, setOpenBooking] = useState<Booking | null>(null);
  const [newBlock, setNewBlock] = useState<AvailabilityBlock | null>(null);

  const week = useMemo(() => weekDays(anchor), [anchor]);
  const range = useMemo(() => {
    const from = startOfWeek(anchor);
    return { from: from.toISOString(), to: addDays(from, 7).toISOString() };
  }, [anchor]);

  const bookingsQuery = useQuery({
    queryKey: ["calendar-bookings", range.from, range.to],
    queryFn: () => listBookings({ startFrom: range.from, startTo: range.to }),
    // Keeps last week on screen while this week loads, so paging weeks does
    // not blank the grid to a skeleton on every click.
    placeholderData: (previous) => previous,
  });

  const availabilityQuery = useQuery({
    queryKey: ["calendar-availability"],
    queryFn: getAvailability,
  });

  const [draft, setDraft] = useState<AvailabilityBlock[] | null>(null);
  const blocks = draft ?? availabilityQuery.data ?? [];
  const dirty = draft !== null;

  const save = useMutation({
    mutationFn: (next: AvailabilityBlock[]) => saveAvailability(next),
    onSuccess: (saved) => {
      setDraft(null);
      queryClient.setQueryData(["calendar-availability"], saved);
      // Availability changes which slots exist, which changes which slots the
      // week grid shows as free.
      queryClient.invalidateQueries({ queryKey: ["calendar-bookings"] });
      toast("Availability saved", "success");
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const markedDates = useMemo(() => {
    const set = new Set<string>();
    for (const booking of bookingsQuery.data ?? []) {
      set.add(dateKey(new Date(booking.start_at)));
    }
    return set;
  }, [bookingsQuery.data]);

  const addBlock = (block: AvailabilityBlock) => {
    setDraft([...blocks, block]);
    setNewBlock(null);
  };

  const removeBlock = (index: number) => {
    setDraft(blocks.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h1 className="text-xl font-semibold">Calendar</h1>
          <p className="text-sm text-muted-foreground">
            Your availability, and every meeting booked through it.
          </p>
        </div>
        {/* A styled <a>, not a <Button> wrapping a <Link>: Button renders a
            real <button>, and a link inside a button is invalid HTML that
            browsers and screen readers each resolve differently. */}
        <Link
          href="/calendar/booking-pages"
          className="inline-flex h-8 items-center gap-2 rounded border border-border px-3 text-xs font-medium hover:bg-muted"
        >
          <Link2 size={14} aria-hidden="true" />
          Booking pages
        </Link>
      </header>

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        {/* ── Sidebar ─────────────────────────────────────────────────── */}
        <div className="space-y-4">
          <Card>
            <CardContent className="pt-gutter">
              <MiniCalendar
                month={month}
                selected={anchor}
                onMonthChange={setMonth}
                onSelect={(day) => {
                  setAnchor(day);
                  setMonth(day);
                }}
                markedDates={markedDates}
              />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex-row items-center justify-between">
              <CardTitle className="text-sm">Weekly availability</CardTitle>
              <Button
                size="sm"
                variant="ghost"
                aria-label="Add an availability block"
                onClick={() =>
                  setNewBlock({
                    day_of_week: 0,
                    start_time: DEFAULT_START,
                    end_time: DEFAULT_END,
                    timezone: browserTimezone(),
                    is_active: true,
                  })
                }
              >
                <Plus size={14} aria-hidden="true" />
              </Button>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <AsyncState
                isLoading={availabilityQuery.isLoading}
                error={availabilityQuery.error}
                empty={blocks.length === 0}
                emptyLabel="No availability set — nobody can book you yet."
              >
                <ul className="space-y-1">
                  {blocks.map((block, index) => (
                    <li
                      key={`${block.day_of_week}-${block.start_time}-${index}`}
                      className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1"
                    >
                      <span className="min-w-0 truncate">
                        <strong>{DAY_LABELS[block.day_of_week]}</strong>{" "}
                        {block.start_time.slice(0, 5)}–{block.end_time.slice(0, 5)}
                        <span className="ml-1 text-xs text-muted-foreground">
                          {block.timezone}
                        </span>
                      </span>
                      <button
                        type="button"
                        onClick={() => removeBlock(index)}
                        aria-label={`Remove ${DAY_LABELS[block.day_of_week]} ${block.start_time}`}
                        className="shrink-0 text-muted-foreground hover:text-[rgb(var(--destructive))]"
                      >
                        <Trash2 size={14} aria-hidden="true" />
                      </button>
                    </li>
                  ))}
                </ul>
              </AsyncState>

              {dirty && (
                <div className="flex justify-end gap-2 pt-1">
                  <Button size="sm" variant="outline" onClick={() => setDraft(null)}>
                    Discard
                  </Button>
                  <Button
                    size="sm"
                    disabled={save.isPending}
                    onClick={() => save.mutate(blocks)}
                  >
                    {save.isPending ? "Saving…" : "Save"}
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── Week grid ───────────────────────────────────────────────── */}
        <div className="space-y-2">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium">
              {week[0].toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
              })}{" "}
              –{" "}
              {week[6].toLocaleDateString(undefined, {
                day: "numeric",
                month: "short",
                year: "numeric",
              })}
            </p>
            <div className="flex gap-1">
              <Button
                size="sm"
                variant="outline"
                onClick={() => setAnchor(addDays(anchor, -7))}
              >
                Previous
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => {
                  const today = new Date();
                  setAnchor(today);
                  setMonth(today);
                }}
              >
                Today
              </Button>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setAnchor(addDays(anchor, 7))}
              >
                Next
              </Button>
            </div>
          </div>

          <AsyncState
            isLoading={bookingsQuery.isLoading}
            error={bookingsQuery.error}
          >
            <WeekGrid
              anchor={anchor}
              bookings={bookingsQuery.data ?? []}
              onSelectBooking={setOpenBooking}
              onSelectSlot={(day, hour) =>
                setNewBlock({
                  // The grid is Monday-first and so is day_of_week, so the
                  // index of the clicked column IS the value.
                  day_of_week: week.findIndex((d) => dateKey(d) === dateKey(day)),
                  start_time: `${String(hour).padStart(2, "0")}:00`,
                  end_time: `${String(Math.min(hour + 1, 23)).padStart(2, "0")}:00`,
                  timezone: browserTimezone(),
                  is_active: true,
                })
              }
            />
          </AsyncState>
        </div>
      </div>

      {openBooking && (
        <BookingDrawer
          booking={openBooking}
          onClose={() => setOpenBooking(null)}
        />
      )}

      {newBlock && (
        <NewAvailabilityModal
          block={newBlock}
          onChange={setNewBlock}
          onCancel={() => setNewBlock(null)}
          onAdd={addBlock}
        />
      )}
    </div>
  );
}

function NewAvailabilityModal({
  block,
  onChange,
  onCancel,
  onAdd,
}: {
  block: AvailabilityBlock;
  onChange: (next: AvailabilityBlock) => void;
  onCancel: () => void;
  onAdd: (block: AvailabilityBlock) => void;
}) {
  const invalid = block.end_time <= block.start_time;

  return (
    <Modal open onClose={onCancel} title="New availability block">
      <div className="space-y-3 text-sm">
        <div className="space-y-1">
          <Label htmlFor="av-day">Day</Label>
          <select
            id="av-day"
            value={block.day_of_week}
            onChange={(event) =>
              onChange({ ...block, day_of_week: Number(event.target.value) })
            }
            className="h-10 w-full rounded border border-border bg-card px-3 text-sm"
          >
            {DAY_LABELS.map((label, index) => (
              <option key={label} value={index}>
                {label}
              </option>
            ))}
          </select>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label htmlFor="av-start">From</Label>
            <Input
              id="av-start"
              type="time"
              value={block.start_time}
              onChange={(event) =>
                onChange({ ...block, start_time: event.target.value })
              }
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="av-end">To</Label>
            <Input
              id="av-end"
              type="time"
              value={block.end_time}
              onChange={(event) =>
                onChange({ ...block, end_time: event.target.value })
              }
            />
          </div>
        </div>

        <div className="space-y-1">
          <Label htmlFor="av-tz">Time zone</Label>
          <Input
            id="av-tz"
            value={block.timezone}
            onChange={(event) =>
              onChange({ ...block, timezone: event.target.value })
            }
            placeholder="Europe/London"
          />
          <p className="text-xs text-muted-foreground">
            These are wall-clock times in this zone, so they stay at the same
            hour of your morning across daylight saving.
          </p>
        </div>

        {invalid && (
          <p role="alert" className="text-xs text-[rgb(var(--destructive))]">
            The end time must be after the start time. Overnight windows are not
            supported.
          </p>
        )}

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button disabled={invalid} onClick={() => onAdd(block)}>
            Add block
          </Button>
        </div>
      </div>
    </Modal>
  );
}
