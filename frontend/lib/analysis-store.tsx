"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import type { AnalyzeResponse } from "./types";

/**
 * Holds the completed assessment between the intake page and the results page.
 *
 * Backed by sessionStorage rather than React state alone so a refresh on
 * /results does not throw away the report the user just waited a minute for.
 * sessionStorage (not localStorage) because a health assessment should not
 * outlive the browser tab.
 */

const RESULT_KEY = "hrp.result";

interface AnalysisValue {
  result: AnalyzeResponse | null;
  setResult: (result: AnalyzeResponse) => void;
  clearResult: () => void;
  /** False until sessionStorage has been read; guards a premature redirect. */
  hydrated: boolean;
}

const AnalysisContext = createContext<AnalysisValue | null>(null);

export function AnalysisProvider({ children }: { children: ReactNode }) {
  const [result, setResultState] = useState<AnalyzeResponse | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(RESULT_KEY);
      if (stored) setResultState(JSON.parse(stored));
    } catch {
      // Corrupt or unreadable payload — start clean instead of crashing the
      // results page on a malformed JSON parse.
      try {
        sessionStorage.removeItem(RESULT_KEY);
      } catch {
        /* nothing further to do */
      }
    }
    setHydrated(true);
  }, []);

  const setResult = useCallback((next: AnalyzeResponse) => {
    setResultState(next);
    try {
      sessionStorage.setItem(RESULT_KEY, JSON.stringify(next));
    } catch {
      // Quota exceeded on a very large assessment: keep it in memory so the
      // current navigation works, and lose it on refresh.
    }
  }, []);

  const clearResult = useCallback(() => {
    setResultState(null);
    try {
      sessionStorage.removeItem(RESULT_KEY);
    } catch {
      /* ignore */
    }
  }, []);

  return (
    <AnalysisContext.Provider
      value={{ result, setResult, clearResult, hydrated }}
    >
      {children}
    </AnalysisContext.Provider>
  );
}

export function useAnalysis(): AnalysisValue {
  const context = useContext(AnalysisContext);
  if (!context) {
    throw new Error("useAnalysis must be used inside <AnalysisProvider>");
  }
  return context;
}
