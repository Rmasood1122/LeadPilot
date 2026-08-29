import { cn } from "@/lib/utils";

/**
 * A progress bar with a real accessible value.
 *
 * role="progressbar" plus aria-valuenow/min/max, not a bare styled div: a
 * screen-reader user otherwise gets no indication of progress at all, which
 * for a page whose entire purpose is tracking progress makes the feature
 * invisible to them.
 *
 * Written by hand rather than pulling in @radix-ui/react-progress (which IS in
 * package.json but has no wrapper in components/ui): this is one div and a
 * width, and adding the dependency's wrapper here would be the only place in
 * the app that uses it.
 */
export function ProgressBar({
  percent,
  label,
  className,
  tone = "primary",
}: {
  percent: number;
  /** Accessible name — what this bar is measuring. */
  label: string;
  className?: string;
  tone?: "primary" | "success";
}) {
  // Clamped defensively: a NaN reaches the DOM as `width: NaN%`, which browsers
  // render as full width — a bar that reads "finished" for a video nobody
  // has started.
  const safe = Number.isFinite(percent)
    ? Math.max(0, Math.min(100, percent))
    : 0;

  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuenow={Math.round(safe)}
      aria-valuemin={0}
      aria-valuemax={100}
      className={cn("h-2 w-full overflow-hidden rounded bg-muted", className)}
    >
      <div
        className={cn(
          "h-full rounded transition-[width] duration-300",
          tone === "success" ? "bg-success" : "bg-primary",
        )}
        style={{ width: `${safe}%` }}
      />
    </div>
  );
}
