"use client";

/** Engagement Hub, Feature 2 — booking pages: the links you hand a prospect.
 *
 * A user can have several ("30-min intro", "60-min technical deep dive") over
 * the same underlying availability, which is why this is a list and not a
 * single settings form.
 *
 * THE SLUG IS NOT EDITABLE AFTER CREATION, and the form says so. Changing it
 * silently breaks every link already sent and every calendar invite already
 * accepted; deleting the page and making a new one is the honest way to change
 * a public URL, because it is a decision rather than a typo.
 */

import { useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Copy, ExternalLink, Plus, Power } from "lucide-react";

import {
  bookingPageUrl,
  createBookingPage,
  deactivateBookingPage,
  listBookingPages,
  updateBookingPage,
  type BookingPage,
  type CustomQuestion,
} from "@/lib/api/calendar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Modal } from "@/components/ui/dialog";
import { Input, Label, Textarea } from "@/components/ui/input";
import { AsyncState } from "@/components/ui/skeleton";
import { useToast } from "@/components/ui/toast";

const DURATIONS = [15, 30, 45, 60];

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export default function BookingPagesPage() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);

  const pagesQuery = useQuery({
    queryKey: ["booking-pages"],
    queryFn: listBookingPages,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["booking-pages"] });

  const toggleActive = useMutation({
    // Two different endpoints, one control. Deactivating is a DELETE (soft:
    // it flips is_active and keeps every booking made through the page);
    // reactivating is a PATCH. The `void` return is what makes them one
    // mutation -- neither result is used, the list is refetched instead.
    mutationFn: async (page: BookingPage): Promise<void> => {
      if (page.is_active) {
        await deactivateBookingPage(page.id);
      } else {
        await updateBookingPage(page.id, { is_active: true });
      }
    },
    onSuccess: () => {
      invalidate();
      toast("Booking page updated", "success");
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const copy = async (slug: string) => {
    const url = bookingPageUrl(slug);
    try {
      await navigator.clipboard.writeText(url);
      toast("Link copied", "success");
    } catch {
      // Clipboard access is denied in some WebViews and over plain HTTP.
      // Showing the URL is a worse experience than copying it, and a much
      // better one than a button that silently does nothing.
      toast(url, "info");
    }
  };

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link
            href="/calendar"
            className="mb-1 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <ArrowLeft size={12} aria-hidden="true" />
            Calendar
          </Link>
          <h1 className="text-xl font-semibold">Booking pages</h1>
          <p className="text-sm text-muted-foreground">
            Public links a prospect can book a slot on. They see only your free
            times.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus size={16} aria-hidden="true" />
          Create booking page
        </Button>
      </header>

      <AsyncState
        isLoading={pagesQuery.isLoading}
        error={pagesQuery.error}
        empty={(pagesQuery.data ?? []).length === 0}
        emptyLabel="No booking pages yet. Create one to start taking meetings."
      >
        <ul className="grid gap-3 sm:grid-cols-2">
          {(pagesQuery.data ?? []).map((page) => (
            <li key={page.id}>
              <Card>
                <CardHeader className="flex-row items-start justify-between gap-2">
                  <div className="min-w-0">
                    <CardTitle className="truncate text-sm">
                      {page.title}
                    </CardTitle>
                    <p className="truncate text-xs text-muted-foreground">
                      /book/{page.slug}
                    </p>
                  </div>
                  <Badge tone={page.is_active ? "success" : "default"}>
                    {page.is_active ? "live" : "paused"}
                  </Badge>
                </CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <p className="text-muted-foreground">
                    {page.duration_minutes} min
                    {page.buffer_minutes > 0 &&
                      ` · ${page.buffer_minutes} min buffer`}
                    {page.max_bookings_per_day != null &&
                      ` · max ${page.max_bookings_per_day}/day`}
                  </p>
                  {page.description && (
                    <p className="line-clamp-2 text-muted-foreground">
                      {page.description}
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => copy(page.slug)}
                    >
                      <Copy size={14} aria-hidden="true" />
                      Copy link
                    </Button>
                    <a
                      href={bookingPageUrl(page.slug)}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="inline-flex h-8 items-center gap-2 rounded border border-border px-3 text-xs font-medium hover:bg-muted"
                    >
                      <ExternalLink size={14} aria-hidden="true" />
                      Preview
                    </a>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={toggleActive.isPending}
                      onClick={() => toggleActive.mutate(page)}
                    >
                      <Power size={14} aria-hidden="true" />
                      {page.is_active ? "Pause" : "Resume"}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            </li>
          ))}
        </ul>
      </AsyncState>

      {creating && (
        <CreateBookingPageModal
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            invalidate();
          }}
        />
      )}
    </div>
  );
}

function CreateBookingPageModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const [title, setTitle] = useState("");
  // Tracked separately from `title` so that typing a title fills the slug,
  // but editing the slug then stops it being overwritten on the next
  // keystroke — the behaviour every CMS has and everybody expects.
  const [slugTouched, setSlugTouched] = useState(false);
  const [slug, setSlug] = useState("");
  const [description, setDescription] = useState("");
  const [duration, setDuration] = useState(30);
  const [questions, setQuestions] = useState<CustomQuestion[]>([]);

  const create = useMutation({
    mutationFn: () =>
      createBookingPage({
        slug: slug || slugify(title),
        title,
        description: description || null,
        duration_minutes: duration,
        custom_questions: questions.filter((q) => q.label.trim()),
      }),
    onSuccess: () => {
      toast("Booking page created", "success");
      onCreated();
    },
    onError: (error) => toast((error as Error).message, "error"),
  });

  const effectiveSlug = slug || slugify(title);

  return (
    <Modal open onClose={onClose} title="Create booking page">
      <div className="space-y-3 text-sm">
        <div className="space-y-1">
          <Label htmlFor="bp-title">Title</Label>
          <Input
            id="bp-title"
            value={title}
            onChange={(event) => {
              setTitle(event.target.value);
              if (!slugTouched) setSlug(slugify(event.target.value));
            }}
            placeholder="Intro call"
          />
        </div>

        <div className="space-y-1">
          <Label htmlFor="bp-slug">Link</Label>
          <div className="flex items-center gap-1">
            <span className="shrink-0 text-xs text-muted-foreground">/book/</span>
            <Input
              id="bp-slug"
              value={slug}
              onChange={(event) => {
                setSlugTouched(true);
                setSlug(slugify(event.target.value));
              }}
              placeholder="intro-call"
            />
          </div>
          <p className="text-xs text-muted-foreground">
            This cannot be changed later — every link you send points at it.
          </p>
        </div>

        <div className="space-y-1">
          <Label htmlFor="bp-duration">Length</Label>
          <select
            id="bp-duration"
            value={duration}
            onChange={(event) => setDuration(Number(event.target.value))}
            className="h-10 w-full rounded border border-border bg-card px-3 text-sm"
          >
            {DURATIONS.map((minutes) => (
              <option key={minutes} value={minutes}>
                {minutes} minutes
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1">
          <Label htmlFor="bp-description">Description</Label>
          <Textarea
            id="bp-description"
            rows={2}
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="What the call covers, and what to bring."
          />
        </div>

        <section aria-label="Custom questions" className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>Questions</Label>
            <Button
              size="sm"
              variant="ghost"
              onClick={() =>
                setQuestions([
                  ...questions,
                  { key: `q${questions.length + 1}`, label: "", required: false },
                ])
              }
            >
              <Plus size={14} aria-hidden="true" />
              Add
            </Button>
          </div>
          {questions.map((question, index) => (
            <div key={question.key} className="flex items-center gap-2">
              <Input
                value={question.label}
                aria-label={`Question ${index + 1}`}
                placeholder="What's the biggest bottleneck right now?"
                onChange={(event) =>
                  setQuestions(
                    questions.map((q, i) =>
                      i === index ? { ...q, label: event.target.value } : q,
                    ),
                  )
                }
              />
              <label className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={!!question.required}
                  onChange={(event) =>
                    setQuestions(
                      questions.map((q, i) =>
                        i === index
                          ? { ...q, required: event.target.checked }
                          : q,
                      ),
                    )
                  }
                  className="h-3.5 w-3.5 accent-[rgb(var(--primary))]"
                />
                Required
              </label>
            </div>
          ))}
        </section>

        <div className="flex justify-end gap-2 pt-1">
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            disabled={!title.trim() || !effectiveSlug || create.isPending}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating…" : "Create"}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
