/**
 * Logo — the one place brand imagery is sized.
 *
 * Two variants, because the source artwork is a square lockup (arrow above a
 * "LEADPILOT" wordmark) and the wordmark is only ~3% of the artwork's height:
 *
 *   LogoMark    the arrow on the brand ground, as a small rounded tile. Used
 *               anywhere the logo sits inline at 20-32px, where the lockup's
 *               wordmark would render sub-pixel and read as a smudge. Paired
 *               with the product name in real text, which stays selectable,
 *               translatable and legible at any zoom.
 *
 *   LogoLockup  the full artwork, for places with room to render it large
 *               enough that the wordmark actually reads (login hero).
 *
 * Plain <img> rather than next/image: the app is a static export
 * (`output: 'export'`, `images.unoptimized: true`), so next/image would add a
 * wrapper for no benefit. Width and height are always set to reserve layout
 * space and avoid a shift on load.
 */

import { cn } from "@/lib/utils";

const LOCKUP_ASPECT = 532 / 528; // measured from the source artwork

export function LogoMark({
  size = 24,
  className,
}: {
  size?: number;
  className?: string;
}) {
  return (
    <img
      src="/icons/icon-192.png"
      width={size}
      height={size}
      /* Decorative: every use sits beside the product name in real text, so
         announcing it again would just repeat "LeadPilot" to a screen reader. */
      alt=""
      aria-hidden="true"
      className={cn("shrink-0 rounded-[22%]", className)}
    />
  );
}

export function LogoLockup({
  width = 132,
  className,
}: {
  width?: number;
  className?: string;
}) {
  return (
    <img
      src="/brand/logo-full.png"
      width={width}
      height={Math.round(width * LOCKUP_ASPECT)}
      /* Not decorative here: this replaces the product name rather than
         accompanying it. */
      alt="LeadPilot"
      className={cn("rounded-xl", className)}
    />
  );
}
