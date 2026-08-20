import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded bg-muted", className)}
    />
  );
}

/** Standard trio: loading skeleton / error / empty — no blank screens. */
export function AsyncState({
  isLoading,
  error,
  empty,
  emptyLabel,
  children,
}: {
  isLoading: boolean;
  error: unknown;
  empty?: boolean;
  emptyLabel?: string;
  children: React.ReactNode;
}) {
  if (isLoading)
    return (
      <div className="space-y-3" role="status" aria-label="Loading">
        <Skeleton className="h-8 w-1/3" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  if (error)
    return (
      <div
        role="alert"
        className="rounded border border-destructive/40 bg-card p-4 text-sm"
      >
        <p className="font-medium text-destructive">Something went wrong</p>
        <p className="text-muted-foreground">
          {error instanceof Error ? error.message : "Unknown error"}
        </p>
      </div>
    );
  if (empty)
    return (
      <div className="rounded border border-dashed border-border p-8 text-center text-sm text-muted-foreground">
        {emptyLabel ?? "Nothing here yet."}
      </div>
    );
  return <>{children}</>;
}
