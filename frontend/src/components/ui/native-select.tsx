import * as React from "react";
import { cn } from "@/lib/utils";

/** A native <select> styled exactly like <Input>. Native on purpose: a
 *  250-country list is the one control where the platform picker (type-ahead
 *  on desktop, the wheel on mobile) beats any custom popover. */
export const NativeSelect = React.forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(({ className, ...props }, ref) => (
  <select
    ref={ref}
    className={cn(
      "flex h-10 w-full rounded border border-border bg-card px-3 py-2 text-sm text-card-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
NativeSelect.displayName = "NativeSelect";
