"use client";

/** Fixed-height row virtualization, hand-rolled.
 *
 * WHY NOT @tanstack/react-virtual OR react-window
 * Neither is already a dependency, and this grid is the easy case for
 * virtualization: every row is exactly the same height, so the visible
 * window is arithmetic — no measurement, no resize observer, no cache
 * invalidation, which is the entire reason those libraries are as large as
 * they are. Sixty lines here avoids adding a runtime dependency (and its
 * transitive tree, and its supply-chain surface) to a static-exported bundle
 * that also ships inside an Android APK.
 *
 * If rows ever become variable-height — an expandable detail row, wrapped
 * multi-line cells — this is the wrong tool and @tanstack/react-virtual is
 * the right one. That is the line to watch.
 *
 * The overscan exists because scrolling is faster than React renders: with
 * none, a fast flick shows blank rows for a frame or two at the leading edge.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface VirtualWindow {
  /** Index of the first row to render. */
  start: number;
  /** Index AFTER the last row to render (exclusive). */
  end: number;
  /** Height of the full list, so the scrollbar is the right size. */
  totalHeight: number;
  /** Pixel offset of `start`, applied as a translate on the rendered slice. */
  offsetY: number;
}

export interface UseVirtualRowsOptions {
  rowCount: number;
  rowHeight: number;
  /** Extra rows rendered above and below the viewport. */
  overscan?: number;
}

export function computeWindow(
  scrollTop: number,
  viewportHeight: number,
  { rowCount, rowHeight, overscan = 8 }: UseVirtualRowsOptions,
): VirtualWindow {
  const totalHeight = rowCount * rowHeight;
  if (rowCount === 0 || rowHeight <= 0) {
    return { start: 0, end: 0, totalHeight: 0, offsetY: 0 };
  }
  // Clamp scrollTop: a browser can report a negative value mid-overscroll on
  // iOS, and a value past the end after the row count shrinks under a filter.
  const clamped = Math.max(0, Math.min(scrollTop, Math.max(0, totalHeight - viewportHeight)));
  const first = Math.floor(clamped / rowHeight);
  const visible = Math.ceil(viewportHeight / rowHeight);
  const start = Math.max(0, first - overscan);
  const end = Math.min(rowCount, first + visible + overscan);
  return { start, end, totalHeight, offsetY: start * rowHeight };
}

export function useVirtualRows(options: UseVirtualRowsOptions) {
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(600);

  const onScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element) return;

    const measure = () => setViewportHeight(element.clientHeight || 600);
    measure();

    // ResizeObserver is absent in jsdom (and in older WebViews). Falling back
    // to the initial measurement keeps the grid rendering a sensible window
    // rather than throwing — a test environment that renders 8 rows instead
    // of 20 is fine; one that crashes is not.
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // A shrinking list (a filter was applied) can leave scrollTop past the new
  // end; without this the grid renders an empty window and looks broken until
  // the user scrolls.
  useEffect(() => {
    const maxScroll = Math.max(0, options.rowCount * options.rowHeight - viewportHeight);
    if (scrollTop > maxScroll) {
      setScrollTop(maxScroll);
      if (scrollRef.current) scrollRef.current.scrollTop = maxScroll;
    }
  }, [options.rowCount, options.rowHeight, viewportHeight, scrollTop]);

  const scrollToRow = useCallback(
    (index: number) => {
      const element = scrollRef.current;
      if (!element) return;
      const top = index * options.rowHeight;
      const bottom = top + options.rowHeight;
      // Only scroll when the row is actually outside the viewport — keyboard
      // navigation within the visible rows must not jump the list.
      if (top < element.scrollTop) {
        element.scrollTop = top;
      } else if (bottom > element.scrollTop + element.clientHeight) {
        element.scrollTop = bottom - element.clientHeight;
      }
    },
    [options.rowHeight],
  );

  return {
    scrollRef,
    onScroll,
    scrollToRow,
    window: computeWindow(scrollTop, viewportHeight, options),
  };
}
