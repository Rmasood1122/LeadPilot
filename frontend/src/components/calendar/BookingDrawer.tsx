"use client";

/** One booking, opened from the week grid.
 *
 * Uses the existing Modal primitive rather than a bespoke drawer — the same
 * reasoning as LeadNotesPanel: the app already has one, it traps focus and
 * handles Escape, and a second overlay implementation is a second set of
 * accessibility bugs.
 */

import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarX2, Link2, Video } from "lucide-react";

import { cancelBooking, updateBooking, type Booking } from "@/lib/api/calendar";
import { createMeeting } from "@/lib/api/meetings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/dialog";
import { Label, Textarea } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { formatTime } from "@/lib/calendar/grid";

const STATUS_TONE: Record<string, "success" | "warning" | "destructive" | "default"> =
  {
    confirmed: "success",
    pending: "warning",
    cancelled: "default",
    no_show: "destructive",
  };

export function BookingDrawer({
  booking,
  onClose,
}: {
  booking: Booking;
  onClose: () => void;
}) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [notes, setNotes] = useState(booking.notes ?? "");

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["calendar-bookings"] });
    queryClient.invalidateQueries({ queryKey: ["meetings"] });
  };

  const saveNotes = useMutation({
    mutationFn: () => updateBooking(booking.id, { notes }),
    onSuccess: () => {
      invalidate();
      toast("Notes saved", "success");
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const cancel = useMutation({
    mutationFn: () => cancelBooking(booking.id),
    onSuccess: () => {
      invalidate();
      toast("Booking cancelled — the invitee has been emailed", "info");
      onClose();
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const startMeetingRecord = useMutation({
    mutationFn: () =>
      createMeeting({
        booking_id: booking.id,
        platform: "custom",
        meeting_url: booking.meeting_link,
      }),
    onSuccess: (meeting) => {
      invalidate();
      if (meeting.platform_error) {
        toast(`Meeting created without a join link: ${meeting.platform_error}`,
              "info");
      } else {
        toast("Meeting created — open it from Meetings", "success");
      }
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const start = new Date(booking.start_at);
  const end = new Date(booking.end_at);

  return (
    <Modal open onClose={onClose} title={booking.invitee_name}>
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={STATUS_TONE[booking.status] ?? "default"}>
            {booking.status.replace(/_/g, " ")}
          </Badge>
          <span className="text-muted-foreground">
            {start.toLocaleDateString()} · {formatTime(start)}–{formatTime(end)}
          </span>
        </div>

        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
          <dt className="text-muted-foreground">Email</dt>
          <dd className="truncate">
            <a
              href={`mailto:${booking.invitee_email}`}
              className="underline underline-offset-2"
            >
              {booking.invitee_email}
            </a>
          </dd>
          {booking.invitee_phone && (
            <>
              <dt className="text-muted-foreground">Phone</dt>
              <dd>{booking.invitee_phone}</dd>
            </>
          )}
          {booking.invitee_timezone && (
            <>
              <dt className="text-muted-foreground">Their zone</dt>
              <dd>{booking.invitee_timezone}</dd>
            </>
          )}
        </dl>

        {booking.meeting_link && (
          <div className="flex items-center gap-2">
            <Link2 size={14} aria-hidden="true" className="text-muted-foreground" />
            <a
              href={booking.meeting_link}
              target="_blank"
              rel="noreferrer noopener"
              className="truncate underline underline-offset-2"
            >
              {booking.meeting_link}
            </a>
          </div>
        )}

        {booking.answers && Object.keys(booking.answers).length > 0 && (
          <section aria-label="Answers">
            <h3 className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Answers
            </h3>
            <dl className="space-y-1">
              {Object.entries(booking.answers).map(([key, value]) => (
                <div key={key}>
                  <dt className="text-xs text-muted-foreground">{key}</dt>
                  <dd className="whitespace-pre-wrap break-words">{value}</dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        <div className="space-y-1">
          <Label htmlFor="booking-notes">Notes</Label>
          <Textarea
            id="booking-notes"
            rows={3}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Context for this call"
          />
          <div className="flex justify-end">
            <Button
              size="sm"
              variant="outline"
              disabled={notes === (booking.notes ?? "") || saveNotes.isPending}
              onClick={() => saveNotes.mutate()}
            >
              Save notes
            </Button>
          </div>
        </div>

        <div className="flex flex-wrap justify-between gap-2 border-t border-border pt-3">
          <Button
            size="sm"
            variant="outline"
            disabled={startMeetingRecord.isPending}
            onClick={() => startMeetingRecord.mutate()}
          >
            <Video size={14} aria-hidden="true" />
            Create meeting record
          </Button>
          <Button
            size="sm"
            variant="destructive"
            disabled={booking.status === "cancelled" || cancel.isPending}
            onClick={() => cancel.mutate()}
          >
            <CalendarX2 size={14} aria-hidden="true" />
            {booking.status === "cancelled" ? "Cancelled" : "Cancel booking"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
