"use client";

/**
 * ThemeProvider — re-export of the real implementation.
 *
 * This file used to be a no-op passthrough shim ("must wrap all UI" per
 * its old comment, but did nothing) — the same class of bug as the
 * earlier QueryProvider stub in this codebase: app/layout.tsx imports
 * ThemeProvider from HERE, but the actual working implementation (state,
 * CSS-variable application, backend sync, no-flash-script-compatible
 * caching) lives in lib/theme/ThemeProvider.tsx, imported everywhere
 * ELSE via useTheme(). Since this file never rendered that real
 * Provider's <ThemeContext.Provider>, useTheme() calls anywhere under
 * the real app tree always saw the Context's DEFAULT value (a no-op
 * setTheme) — clicking any preset in Settings appeared to work (local
 * component state updated) but never actually applied a CSS variable or
 * persisted anything. Re-exporting fixes both ends from one place. */
export { ThemeProvider, useTheme } from "@/lib/theme/ThemeProvider";