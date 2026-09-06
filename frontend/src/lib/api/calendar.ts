/** Engagement Hub, Feature 2 — calendar domain module.
 *
 *  Built on the SAME api() client as every other module in this directory.
 *  No second HTTP client, no direct fetch — with one deliberate exception
 *  documented on `publicSlots`/`publicBook` below.
 */

import { api, BASE } from "./client";

// --------------------------------------------------------------------------
// Types
// --------------------------------------------------------------------------

export type BookingStatus = "pending" | "confirmed" | "cancelled" | "no_show";

export interface AvailabilityBlock {
  id?: string;
  /** 0 = Monday .. 6 = Sunday — datetime.weekday(), matching the backend. */
  day_of_week: number;
  /** "HH:MM" or "HH:MM:SS". The backend column is a TIME, not a timestamp. */
  start_time: string;
  end_time: string;
  timezone: string;
  is_active: boolean;
}

export interface CustomQuestion {
  key: string;
  label: string;
  type?: "text" | "textarea";
  required?: boolean;
}

export interface BookingPage {
  id: string;
  slug: string;
  title: string;
  description: string | null;
  duration_minutes: number;
  buffer_minutes: number;
  max_bookings_per_day: number | null;
  custom_questions: CustomQuestion[] | null;
  is_active: boolean;
}

export interface PublicBookingPage {
  slug: string;
  title: string;
  description: string | null;
  duration_minutes: number;
  custom_questions: CustomQuestion[];
}

export interface Slot {
  start_at: string;
  end_at: string;
  /** Local date in the requested timezone — see the backend's note on why
   *  this is not derived from start_at in the browser. */
  date: string;
}

export interface Booking {
  id: string;
  booking_page_id: string;
  invitee_name: string;
  invitee_email: string;
  invitee_phone: string | null;
  invitee_timezone: string | null;
  start_at: string;
  end_at: string;
  meeting_link: string | null;
  status: BookingStatus;
  lead_id: string | null;
  notes: string | null;
  answers: Record<string, string> | null;
}

export interface BookingConfirmation {
  id: string;
  start_at: string;
  end_at: string;
  status: BookingStatus;
  meeting_link: string | null;
  title: string;
}

// --------------------------------------------------------------------------
// Availability
// --------------------------------------------------------------------------

export function getAvailability(): Promise<AvailabilityBlock[]> {
  return api("/calendar/availability");
}

/** Replaces the WHOLE weekly schedule.
 *
 *  A PUT of the complete set, not per-block writes: what the user edits is a
 *  week — drag one, delete one, add one, Save — and splitting that into three
 *  request kinds means a partial failure leaves a schedule nobody ever saw. */
export function saveAvailability(
  blocks: AvailabilityBlock[],
): Promise<AvailabilityBlock[]> {
  return api("/calendar/availability", { method: "PUT", body: { blocks } });
}

// --------------------------------------------------------------------------
// Booking pages
// --------------------------------------------------------------------------

export function listBookingPages(): Promise<BookingPage[]> {
  return api("/calendar/booking-pages");
}

export function createBookingPage(body: {
  slug: string;
  title: string;
  description?: string | null;
  duration_minutes: number;
  buffer_minutes?: number;
  max_bookings_per_day?: number | null;
  custom_questions?: CustomQuestion[];
}): Promise<BookingPage> {
  return api("/calendar/booking-pages", { method: "POST", body });
}

export function updateBookingPage(
  pageId: string,
  patch: Partial<Omit<BookingPage, "id" | "slug">>,
): Promise<BookingPage> {
  return api(`/calendar/booking-pages/${pageId}`, {
    method: "PATCH",
    body: patch,
  });
}

/** Deactivates. Never deletes the row — see the backend handler: a hard
 *  delete would cascade to every booking made through the page. */
export function deactivateBookingPage(pageId: string): Promise<void> {
  return api(`/calendar/booking-pages/${pageId}`, { method: "DELETE" });
}

/** The link to hand to a prospect.
 *
 *  Reads NEXT_PUBLIC_APP_URL when set, and falls back to the origin the app
 *  is being served from. It cannot be derived from BASE: that is the API
 *  origin, and the booking page is a frontend route. */
export function bookingPageUrl(slug: string): string {
  const origin =
    process.env.NEXT_PUBLIC_APP_URL ??
    (typeof window !== "undefined" ? window.location.origin : "");
  return `${origin}/book/${slug}`;
}

// --------------------------------------------------------------------------
// PUBLIC endpoints (no auth)
// --------------------------------------------------------------------------
//
// `auth: false` on all three, deliberately. The visitor booking a call has no
// session, and api() would otherwise attach whatever token happens to be in
// storage — which on a shared machine means one person's booking page request
// carrying another person's credentials to the API for no reason.

export function getPublicBookingPage(
  slug: string,
): Promise<PublicBookingPage> {
  return api(`/calendar/booking-pages/${encodeURIComponent(slug)}/public`, {
    auth: false,
  });
}

export function getPublicSlots(
  slug: string,
  timezone: string,
  days = 30,
): Promise<Slot[]> {
  const q = new URLSearchParams({ timezone, days: String(days) });
  return api(
    `/calendar/booking-pages/${encodeURIComponent(slug)}/slots?${q}`,
    { auth: false },
  );
}

export function bookPublicSlot(
  slug: string,
  body: {
    start_at: string;
    invitee_name: string;
    invitee_email: string;
    invitee_phone?: string | null;
    invitee_timezone?: string | null;
    notes?: string | null;
    answers?: Record<string, string>;
  },
): Promise<BookingConfirmation> {
  return api(`/calendar/booking-pages/${encodeURIComponent(slug)}/book`, {
    method: "POST",
    body,
    auth: false,
  });
}

// --------------------------------------------------------------------------
// Bookings (authenticated)
// --------------------------------------------------------------------------

export function listBookings(params: {
  startFrom?: string;
  startTo?: string;
  status?: BookingStatus;
  leadId?: string;
} = {}): Promise<Booking[]> {
  const q = new URLSearchParams();
  if (params.startFrom) q.set("start_from", params.startFrom);
  if (params.startTo) q.set("start_to", params.startTo);
  if (params.status) q.set("status", params.status);
  if (params.leadId) q.set("lead_id", params.leadId);
  const qs = q.toString();
  return api(`/calendar/bookings${qs ? `?${qs}` : ""}`);
}

export function updateBooking(
  bookingId: string,
  patch: { status?: BookingStatus; notes?: string; meeting_link?: string },
): Promise<Booking> {
  return api(`/calendar/bookings/${bookingId}`, {
    method: "PATCH",
    body: patch,
  });
}

export function cancelBooking(
  bookingId: string,
  reason?: string,
): Promise<void> {
  const q = reason ? `?reason=${encodeURIComponent(reason)}` : "";
  return api(`/calendar/bookings/${bookingId}${q}`, { method: "DELETE" });
}

/** Re-exported so the public booking page can show which API it is talking
 *  to in an error message. Not used for building request URLs. */
export { BASE as API_BASE };
