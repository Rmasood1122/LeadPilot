"use client";

/**
 * The tutorial video player.
 *
 * Two states, and which one renders is decided by the DATA, not by a prop:
 *
 *   is_placeholder (youtube_id is null)
 *       A "not published yet" panel. NOT an <iframe> — an iframe pointing at
 *       a made-up id renders YouTube's own "Video unavailable" error, which
 *       looks exactly like a bug in this app. The catalogue deliberately uses
 *       null rather than a fake id so this branch is reachable and honest.
 *
 *   a real youtube_id
 *       A youtube-nocookie embed with enablejsapi=1, plus the IFrame API
 *       polling playback position so progress records itself.
 *
 * WHY THE IFRAME API AND NOT A TIMER
 * A wall-clock timer cannot tell playing from paused, cannot see a seek, and
 * keeps counting in a background tab — it measures how long the page was open,
 * not how much was watched. The IFrame API reports the real position.
 *
 * VERIFIED against a real video on 2026-08-30 using a throwaway id: the API
 * built an iframe on youtube-nocookie.com carrying the right origin, and the
 * LIVE player answered getDuration() with 214 -- which is only possible if
 * postMessage is being accepted, i.e. if progress polling actually works.
 * That run also caught two real bugs: a missing `origin` (YouTube "Error 153",
 * and silently dead postMessage) and the IFrame API defaulting to youtube.com
 * rather than the nocookie host this file claimed to use.
 *
 * Still unverified: nothing has been watched end to end at normal speed, so
 * the 90%-completion crossing has only ever been exercised through the unit
 * tests and the API. The catalogue ships with all nine ids as null.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { PlayCircle, VideoOff } from "lucide-react";
import {
  REPORT_INTERVAL_MS,
  shouldReportProgress,
  youtubeEmbedUrl,
} from "@/lib/tutorial-progress";
import type { Tutorial } from "@/lib/api/types";

const YT_API_SRC = "https://www.youtube.com/iframe_api";

/** Minimal shape of the bits of the YouTube IFrame API this component uses. */
interface YTPlayer {
  getCurrentTime: () => number;
  getDuration: () => number;
  getPlayerState: () => number;
  destroy: () => void;
}
declare global {
  interface Window {
    YT?: {
      Player: new (el: HTMLElement, opts: Record<string, unknown>) => YTPlayer;
      PlayerState?: { PLAYING: number };
    };
    onYouTubeIframeAPIReady?: () => void;
  }
}

/** YT.PlayerState.PLAYING is 1. Hard-coded because the enum is only present
 *  once the API script has loaded, and this is checked inside the poll. */
const STATE_PLAYING = 1;

/**
 * Load the IFrame API script once per page, not once per player.
 *
 * YouTube's script calls a single global `onYouTubeIframeAPIReady`, so two
 * components racing to define it means one of them never gets its callback.
 * One shared promise removes the race.
 */
let apiPromise: Promise<void> | null = null;
function loadYouTubeApi(): Promise<void> {
  if (typeof window === "undefined") return Promise.resolve();
  if (window.YT?.Player) return Promise.resolve();
  if (apiPromise) return apiPromise;

  apiPromise = new Promise<void>((resolve) => {
    const previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previous?.();
      resolve();
    };
    if (!document.querySelector(`script[src="${YT_API_SRC}"]`)) {
      const script = document.createElement("script");
      script.src = YT_API_SRC;
      script.async = true;
      document.head.appendChild(script);
    }
  });
  return apiPromise;
}

export function VideoPlayer({
  tutorial,
  onProgress,
}: {
  tutorial: Tutorial;
  /** Called when a position is worth persisting. */
  onProgress: (positionSeconds: number, durationSeconds: number | null) => void;
}) {
  const mountRef = useRef<HTMLDivElement | null>(null);
  const playerRef = useRef<YTPlayer | null>(null);
  const lastPositionRef = useRef(0);
  const lastReportAtRef = useRef(0);
  const [apiFailed, setApiFailed] = useState(false);

  // Held in a ref so the polling interval never has to be torn down and
  // rebuilt when the callback identity changes — a rebuilt interval resets
  // the heartbeat and can drop a report.
  const onProgressRef = useRef(onProgress);
  useEffect(() => {
    onProgressRef.current = onProgress;
  }, [onProgress]);

  const completedRef = useRef(tutorial.progress.completed);
  useEffect(() => {
    completedRef.current = tutorial.progress.completed;
  }, [tutorial.progress.completed]);

  const poll = useCallback(() => {
    const player = playerRef.current;
    if (!player) return;
    let state: number;
    let position: number;
    let duration: number;
    try {
      state = player.getPlayerState();
      position = player.getCurrentTime();
      duration = player.getDuration();
    } catch {
      // The iframe can be mid-teardown; skipping one tick is correct.
      return;
    }
    if (state !== STATE_PLAYING) return;

    const now = Date.now();
    const decided = shouldReportProgress({
      lastPositionSeconds: lastPositionRef.current,
      positionSeconds: position,
      lastReportAtMs: lastReportAtRef.current,
      nowMs: now,
      durationSeconds: duration > 0 ? duration : null,
      completedAlready: completedRef.current,
    });
    if (!decided) return;

    lastPositionRef.current = position;
    lastReportAtRef.current = now;
    onProgressRef.current(position, duration > 0 ? duration : null);
  }, []);

  useEffect(() => {
    if (tutorial.is_placeholder || !tutorial.youtube_id) return;
    let cancelled = false;
    let timer: ReturnType<typeof setInterval> | null = null;

    loadYouTubeApi()
      .then(() => {
        if (cancelled || !mountRef.current || !window.YT?.Player) return;
        playerRef.current = new window.YT.Player(mountRef.current, {
          // The IFrame API builds its OWN embed URL and defaults to
          // youtube.com. Without this the privacy-preserving host was used
          // only by the fallback <iframe> below, while the path almost every
          // user actually takes quietly loaded the tracking host -- a
          // discrepancy the code claimed not to have. Verified in a browser:
          // the generated src now carries youtube-nocookie.com.
          host: "https://www.youtube-nocookie.com",
          videoId: tutorial.youtube_id,
          playerVars: {
            enablejsapi: 1,
            rel: 0,
            modestbranding: 1,
            playsinline: 1,
            // REQUIRED whenever enablejsapi=1.
            //
            // Without it YouTube renders "Error 153 — Video player
            // configuration error" and, worse, silently rejects the
            // postMessage traffic the IFrame API uses -- so the player would
            // look fine while getCurrentTime() never reported anything and
            // progress never advanced. Caught by loading the real embed URL
            // in a browser, which showed Error 153 on a valid video id.
            origin: typeof window !== "undefined" ? window.location.origin : undefined,
            // Resume where they left off. Not applied when the video is
            // already finished — restarting a completed video at 90% is
            // annoying, and rewatching is the likely intent.
            start: tutorial.progress.completed
              ? 0
              : Math.floor(tutorial.progress.position_seconds || 0),
          },
        });
        // Poll rather than relying on onStateChange: a state event fires on
        // play/pause but NOT while playback simply continues, so position
        // would only ever be recorded at the moment someone paused.
        timer = setInterval(poll, Math.min(REPORT_INTERVAL_MS, 5_000));
      })
      .catch(() => {
        if (!cancelled) setApiFailed(true);
      });

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
      try {
        playerRef.current?.destroy();
      } catch {
        /* already gone */
      }
      playerRef.current = null;
    };
    // tutorial.slug, not the whole object: progress updates change the object
    // identity constantly, and rebuilding the player on every progress write
    // would restart the video every few seconds.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tutorial.slug, tutorial.youtube_id, tutorial.is_placeholder, poll]);

  if (tutorial.is_placeholder || !tutorial.youtube_id) {
    return (
      <div
        data-testid="video-placeholder"
        className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded border border-dashed border-border bg-muted/40 p-6 text-center"
      >
        <VideoOff size={32} className="text-muted-foreground" aria-hidden="true" />
        <p className="font-medium">This video is not published yet</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          The lesson outline is below. You can still mark it complete if you
          already know the material.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full">
      <div className="relative aspect-video w-full overflow-hidden rounded bg-black">
        {/* The API replaces this node with its own iframe. Until it does — or
            if the script is blocked — a plain iframe is still rendered by the
            noscript-style fallback below, so the video is watchable even
            when progress cannot be tracked. */}
        <div ref={mountRef} className="h-full w-full" data-testid="yt-mount" />
        {apiFailed && (
          <iframe
            data-testid="yt-fallback-iframe"
            className="absolute inset-0 h-full w-full"
            src={youtubeEmbedUrl(tutorial.youtube_id, {
              startSeconds: tutorial.progress.completed
                ? 0
                : tutorial.progress.position_seconds,
              origin: typeof window !== "undefined"
                ? window.location.origin : undefined,
            })}
            title={tutorial.title}
            allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        )}
      </div>
      {apiFailed && (
        <p role="status" className="mt-2 text-xs text-muted-foreground">
          <PlayCircle size={12} className="mr-1 inline" aria-hidden="true" />
          Progress tracking is unavailable (the YouTube player script could not
          load). Use &ldquo;Mark complete&rdquo; when you finish.
        </p>
      )}
    </div>
  );
}
