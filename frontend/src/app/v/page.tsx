"use client";

/** Feature Group 2 — the PUBLIC page behind step 2's personal-video link.
 *
 * Opened by a prospect from an email, so: no auth, outside the (app) group
 * (no Shell, no session guard), and it shows only what the token unlocks -- a
 * first name, a company and the Loom embed. `/v?t=<token>` rather than a
 * dynamic segment for the same static-export reason as /book. */

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";

import { getPublicVideo } from "@/lib/api/personalization";

function VideoPage() {
  const token = useSearchParams().get("t") ?? "";
  const query = useQuery({
    queryKey: ["public-video", token],
    queryFn: () => getPublicVideo(token),
    enabled: token.length > 0,
    retry: false,
  });

  if (!token || query.error) {
    return (
      <p className="text-center text-sm text-muted-foreground">
        This video link is no longer available.
      </p>
    );
  }
  if (query.isLoading || !query.data) {
    return <p className="text-center text-sm text-muted-foreground">Loading…</p>;
  }
  const video = query.data;
  return (
    <div className="space-y-4">
      <h1 className="text-center text-2xl font-semibold">
        Hi {video.first_name}{video.company ? ` — a quick video for ${video.company}` : ""}
      </h1>
      {video.title && <p className="text-center text-muted-foreground">{video.title}</p>}
      <div className="relative w-full overflow-hidden rounded-lg border border-border" style={{ paddingTop: "56.25%" }}>
        <iframe
          src={video.embed_url}
          title={video.title ?? "Personal video"}
          className="absolute inset-0 h-full w-full"
          allow="fullscreen"
          allowFullScreen
        />
      </div>
    </div>
  );
}

export default function PublicVideoRoute() {
  return (
    <main className="mx-auto min-h-dvh max-w-3xl bg-background p-6 text-foreground">
      <Suspense fallback={null}>
        <VideoPage />
      </Suspense>
    </main>
  );
}
