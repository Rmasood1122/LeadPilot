"use client";

/**
 * A section that eases in the first time it scrolls into view.
 *
 * The exported HTML never hides anything: `data-reveal` is set only after
 * hydration, only for sections still below the fold, and only when the
 * visitor has not asked for reduced motion (src/lib/homeMotion.ts
 * revealMode). So no JavaScript, slow JavaScript or reduced motion all mean
 * "content is simply there".
 */

import { useEffect, useRef } from "react";

import { prefersReducedMotion, revealMode } from "@/lib/homeMotion";

export function Reveal({ children, className, as: Tag = "div" }: {
  children: React.ReactNode;
  className?: string;
  as?: "div" | "section";
}) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const mode = revealMode({
      reducedMotion: prefersReducedMotion(),
      hasObserver: typeof IntersectionObserver !== "undefined",
    });
    if (mode === "static") return;
    // Already on screen (or above it): leave it alone, never hide visible text.
    if (el.getBoundingClientRect().top < window.innerHeight * 0.9) return;
    el.dataset.reveal = "pending";
    const io = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting) return;
        el.dataset.reveal = "shown";
        io.disconnect();
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <Tag ref={ref as React.Ref<HTMLDivElement>} className={className}>
      {children}
    </Tag>
  );
}
