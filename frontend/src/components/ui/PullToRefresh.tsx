'use client';

/**
 * PullToRefresh — ClientHunter Enterprise
 *
 * Touch-event pull-to-refresh wrapper for use on the leads kanban
 * and campaign stats views.
 *
 * How it works:
 *   • Intercepts touchstart/touchmove/touchend on the wrapped element.
 *   • Only triggers when the scroll container is already at the top (scrollTop === 0).
 *   • At the threshold distance: fires @capacitor/haptics light-impact feedback
 *     and calls the onRefresh callback (typically a React Query refetch()).
 *   • Shows a simple visual indicator during pull and refresh.
 *
 * Web: works via mouse events too (mousedown/mousemove/mouseup) for dev testing.
 *
 * TODO: verify @capacitor/haptics API shape against current Capacitor docs.
 */

import {
  useRef,
  useState,
  useCallback,
  ReactNode,
  TouchEvent,
  CSSProperties,
} from 'react';
import { isNative } from '@/lib/platform';

const PULL_THRESHOLD_PX = 72;   // how far to pull before triggering
const PULL_RESISTANCE  = 0.4;   // visual damping factor

interface PullToRefreshProps {
  onRefresh: () => Promise<void>;
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
  disabled?: boolean;
}

type Phase = 'idle' | 'pulling' | 'refreshing';

async function hapticLight() {
  if (!isNative()) return;
  try {
    // TODO: verify @capacitor/haptics ImpactStyle.Light value
    const { Haptics, ImpactStyle } = await import('@capacitor/haptics');
    await Haptics.impact({ style: ImpactStyle.Light });
  } catch {
    // Non-fatal — haptics are a nice-to-have
  }
}

export function PullToRefresh({
  onRefresh,
  children,
  className,
  style,
  disabled = false,
}: PullToRefreshProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const startYRef = useRef(0);
  const [phase, setPhase] = useState<Phase>('idle');
  const [pullDistance, setPullDistance] = useState(0);
  const hapticFiredRef = useRef(false);

  const handleTouchStart = useCallback((e: TouchEvent<HTMLDivElement>) => {
    if (disabled || phase === 'refreshing') return;
    const el = containerRef.current;
    if (!el || el.scrollTop > 0) return;  // only trigger at top of scroll
    startYRef.current = e.touches[0].clientY;
    hapticFiredRef.current = false;
    setPhase('pulling');
  }, [disabled, phase]);

  const handleTouchMove = useCallback((e: TouchEvent<HTMLDivElement>) => {
    if (phase !== 'pulling') return;
    const el = containerRef.current;
    if (!el || el.scrollTop > 0) {
      // User scrolled down while pulling — cancel
      setPhase('idle');
      setPullDistance(0);
      return;
    }

    const deltaY = e.touches[0].clientY - startYRef.current;
    if (deltaY <= 0) {
      setPhase('idle');
      setPullDistance(0);
      return;
    }

    // Apply resistance so the indicator doesn't fly off screen
    const visual = Math.min(deltaY * PULL_RESISTANCE, PULL_THRESHOLD_PX * 1.4);
    setPullDistance(visual);

    // Haptic at threshold
    if (deltaY >= PULL_THRESHOLD_PX && !hapticFiredRef.current) {
      hapticFiredRef.current = true;
      hapticLight();
    }
  }, [phase]);

  const handleTouchEnd = useCallback(async () => {
    if (phase !== 'pulling') return;

    if (pullDistance >= PULL_THRESHOLD_PX * PULL_RESISTANCE) {
      setPhase('refreshing');
      setPullDistance(0);
      try {
        await onRefresh();
      } finally {
        setPhase('idle');
      }
    } else {
      setPhase('idle');
      setPullDistance(0);
    }
  }, [phase, pullDistance, onRefresh]);

  const indicatorStyle: CSSProperties = {
    position: 'absolute',
    top: 0,
    left: '50%',
    transform: `translateX(-50%) translateY(${
      phase === 'refreshing' ? '12px' : `${pullDistance - 36}px`
    })`,
    transition: phase === 'refreshing' ? 'transform 200ms ease' : 'none',
    opacity: phase === 'idle' ? 0 : Math.min(pullDistance / (PULL_THRESHOLD_PX * PULL_RESISTANCE), 1),
    zIndex: 10,
    pointerEvents: 'none',
  };

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ position: 'relative', overflowY: 'auto', ...style }}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Pull indicator */}
      <div style={indicatorStyle}>
        <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--color-primary)] shadow-lg">
          <svg
            className={`h-5 w-5 text-white ${phase === 'refreshing' ? 'animate-spin' : ''}`}
            fill="none"
            stroke="currentColor"
            strokeWidth={2.5}
            viewBox="0 0 24 24"
            aria-hidden="true"
            style={phase !== 'refreshing' ? {
              transform: `rotate(${Math.min((pullDistance / (PULL_THRESHOLD_PX * PULL_RESISTANCE)) * 360, 360)}deg)`,
            } : undefined}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
          </svg>
        </div>
      </div>

      {children}
    </div>
  );
}
