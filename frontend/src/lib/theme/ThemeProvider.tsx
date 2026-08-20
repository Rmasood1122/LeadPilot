"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import type { Theme } from "./types";
import { DEFAULT_THEME } from "./types";
import { PRESETS } from "./presets";
import { applyTheme, themeToCssVars } from "./apply";
import { relativeLuminance } from "./contrast";
import { getTheme } from "@/lib/api/themes";
import { hasSession } from "@/lib/api/client";

interface ThemeContextValue {
  theme: Theme;
  /** Apply without persisting (live preview + optimistic updates). */
  setTheme: (t: Theme) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: DEFAULT_THEME,
  setTheme: () => undefined,
});

export function useTheme() {
  return useContext(ThemeContext);
}

// The no-flash inline script in app/layout.tsx reads sessionStorage's
// "ch_theme" key, expecting { cssVars: {...}, darkMode: boolean } — NOT
// a raw Theme object. Kept in one place so save/read never drift apart
// again (this mismatch — this file writing "leadpilot.theme" to
// localStorage as a raw Theme, while layout.tsx's script read a
// differently-shaped "ch_theme" from sessionStorage — was the actual bug:
// every reload silently fell back to DEFAULT_THEME's colors, discarding
// whatever preset/customization the user had picked).
const THEME_STORAGE_KEY = "ch_theme";

function cacheForNoFlash(t: Theme) {
  try {
    sessionStorage.setItem(
      THEME_STORAGE_KEY,
      JSON.stringify({
        cssVars: themeToCssVars(t),
        darkMode: relativeLuminance(t.background_color) < 0.35,
        raw: t, // extra field, ignored by the no-flash script; lets
                // React's initial state below match on remount too
      }),
    );
  } catch {
    /* storage full/blocked — theme still applies for this session */
  }
}

function readCachedTheme(): Theme {
  if (typeof window === "undefined") return DEFAULT_THEME;
  try {
    const raw = sessionStorage.getItem(THEME_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.raw) return { ...DEFAULT_THEME, ...parsed.raw };
    }
  } catch {
    /* corrupted cache — fall through to default */
  }
  return DEFAULT_THEME;
}

/** Loads the saved theme from the backend on login, applies it as CSS
 *  variables on <html>, and caches it (in the shape layout.tsx's no-flash
 *  inline script expects) for the next page load. */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readCachedTheme);

  const setTheme = useCallback((t: Theme) => {
    setThemeState(t);
    applyTheme(t);
    cacheForNoFlash(t);
  }, []);

  useEffect(() => {
    applyTheme(theme);
    if (!hasSession()) return;
    getTheme()
      .then((saved) => {
        if (saved && Object.keys(saved).length > 0) {
          const preset = saved.preset && PRESETS[saved.preset];
          setTheme({ ...(preset ?? DEFAULT_THEME), ...saved, preset: (saved.preset ?? null) } as Theme);
        }
      })
      .catch(() => undefined); // offline/expired: cached theme stands
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}