// SHELVED — the app currently runs the classic "archival" theme only (set
// statically via data-theme on <html>). This provider and the ThemeToggle are
// kept dormant (not mounted anywhere) so the alternate "hacker" theme can be
// brought back when we revisit styling. The hacker palette also still lives in
// index.css.
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import type { ReactNode } from 'react';

export type Theme = 'archival' | 'hacker';

const STORAGE_KEY = 'supervoid.theme';

export const THEME_LABELS: Record<Theme, string> = {
  archival: 'Archive',
  hacker: 'Terminal',
};

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  toggle: () => void;
}

const ThemeContext = createContext<ThemeState | null>(null);

function readStored(): Theme {
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    if (value === 'archival' || value === 'hacker') return value;
  } catch {
    /* private mode etc. */
  }
  return 'archival';
}

function persist(theme: Theme): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, theme);
  } catch {
    /* ignore */
  }
}

function apply(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme);
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(readStored);

  useEffect(() => {
    apply(theme);
  }, [theme]);

  const setTheme = useCallback((next: Theme) => {
    persist(next);
    setThemeState(next);
  }, []);

  const toggle = useCallback(() => {
    setThemeState((current) => {
      const next: Theme = current === 'archival' ? 'hacker' : 'archival';
      persist(next);
      return next;
    });
  }, []);

  const value = useMemo<ThemeState>(
    () => ({ theme, setTheme, toggle }),
    [theme, setTheme, toggle],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeState {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>.');
  return ctx;
}
