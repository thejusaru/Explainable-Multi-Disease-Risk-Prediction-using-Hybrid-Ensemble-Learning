"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { EngineKind } from "./types";

/**
 * Theme and engine preferences, persisted to localStorage.
 *
 * The theme is applied to <html data-theme> by an inline script in layout.tsx
 * *before* first paint; this provider keeps React in sync afterwards. Doing it
 * only here would flash the wrong theme on every page load.
 */

export type ThemeChoice = "light" | "dark" | "system";

const THEME_KEY = "hrp.theme";
const ENGINE_KEY = "hrp.engine";
const MODEL_KEY = "hrp.model";

interface SettingsValue {
  theme: ThemeChoice;
  setTheme: (theme: ThemeChoice) => void;
  /** The theme actually in effect, with "system" resolved. */
  resolvedTheme: "light" | "dark";

  engine: EngineKind | null;
  model: string | null;
  setEngineSelection: (engine: EngineKind, model: string) => void;

  /** False until localStorage has been read, so the UI can avoid flicker. */
  hydrated: boolean;
}

const SettingsContext = createContext<SettingsValue | null>(null);

function systemTheme(): "light" | "dark" {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

function applyTheme(choice: ThemeChoice): "light" | "dark" {
  const resolved = choice === "system" ? systemTheme() : choice;
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("data-theme", resolved);
    document.documentElement.style.colorScheme = resolved;
  }
  return resolved;
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<ThemeChoice>("system");
  const [resolvedTheme, setResolvedTheme] = useState<"light" | "dark">("light");
  const [engine, setEngine] = useState<EngineKind | null>(null);
  const [model, setModel] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Read persisted values once on mount.
  useEffect(() => {
    try {
      const storedTheme = localStorage.getItem(THEME_KEY) as ThemeChoice | null;
      const choice =
        storedTheme === "light" || storedTheme === "dark" || storedTheme === "system"
          ? storedTheme
          : "system";
      setThemeState(choice);
      setResolvedTheme(applyTheme(choice));

      const storedEngine = localStorage.getItem(ENGINE_KEY);
      if (storedEngine === "claude" || storedEngine === "local") {
        setEngine(storedEngine);
      }
      const storedModel = localStorage.getItem(MODEL_KEY);
      if (storedModel) setModel(storedModel);
    } catch {
      // localStorage can throw in private mode or with storage disabled —
      // fall back to defaults rather than breaking the app.
      setResolvedTheme(applyTheme("system"));
    }
    setHydrated(true);
  }, []);

  // Follow the OS when the user has chosen "system".
  useEffect(() => {
    if (theme !== "system" || typeof window === "undefined") return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setResolvedTheme(applyTheme("system"));
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [theme]);

  const setTheme = useCallback((choice: ThemeChoice) => {
    setThemeState(choice);
    setResolvedTheme(applyTheme(choice));
    try {
      localStorage.setItem(THEME_KEY, choice);
    } catch {
      /* preference is lost on reload, but the app still works */
    }
  }, []);

  const setEngineSelection = useCallback(
    (nextEngine: EngineKind, nextModel: string) => {
      setEngine(nextEngine);
      setModel(nextModel);
      try {
        localStorage.setItem(ENGINE_KEY, nextEngine);
        localStorage.setItem(MODEL_KEY, nextModel);
      } catch {
        /* as above */
      }
    },
    [],
  );

  return (
    <SettingsContext.Provider
      value={{
        theme,
        setTheme,
        resolvedTheme,
        engine,
        model,
        setEngineSelection,
        hydrated,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsValue {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used inside <SettingsProvider>");
  }
  return context;
}
