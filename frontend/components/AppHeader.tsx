"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { listEngines } from "../lib/api";
import { useSettings } from "../lib/settings";
import type { EngineOption } from "../lib/types";
import {
  MoonIcon,
  PulseIcon,
  SlidersIcon,
  SunIcon,
} from "./Icons";

/**
 * Persistent header: brand, active-model chip, theme toggle.
 *
 * The chip both displays the current engine and links to /settings, so the
 * selection is always visible and always one click from being changed.
 */
export default function AppHeader() {
  const pathname = usePathname();
  const { engine, model, resolvedTheme, setTheme, hydrated, setEngineSelection } =
    useSettings();

  const [engines, setEngines] = useState<EngineOption[]>([]);

  // Load the engine list once settings have hydrated, so a stored selection
  // isn't overwritten by the default before it has been read.
  useEffect(() => {
    if (!hydrated) return;
    let cancelled = false;

    listEngines()
      .then((response) => {
        if (cancelled) return;
        setEngines(response.engines);

        // Adopt a sensible default only when nothing is stored yet, or when the
        // stored engine is no longer available (key removed, Ollama stopped).
        const stored = response.engines.find((e) => e.kind === engine);
        if (!engine || !stored?.available) {
          const fallback =
            response.engines.find(
              (e) => e.kind === response.default && e.available,
            ) ?? response.engines.find((e) => e.available);
          if (fallback) setEngineSelection(fallback.kind, fallback.model);
        }
      })
      .catch(() => {
        /* Header degrades to "not configured"; pages surface the real error. */
      });

    return () => {
      cancelled = true;
    };
  }, [hydrated, engine, setEngineSelection]);

  const active = engines.find((e) => e.kind === engine);
  const isAvailable = Boolean(active?.available);

  const label =
    active?.kind === "local"
      ? "Local"
      : active?.kind === "claude"
        ? "Cloud"
        : "Model";
  const displayModel = model ?? active?.model ?? "not configured";

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link href="/" className="brand">
          <span className="brand-mark">
            <PulseIcon size={17} />
          </span>
          <span className="brand-text">
            <span className="brand-name">Vitalis</span>
            <span className="brand-sub">Health Risk Projection</span>
          </span>
        </Link>

        <div className="header-actions">
          <Link
            href="/settings"
            className="model-chip"
            title={
              isAvailable
                ? `Using ${displayModel} — click to change`
                : "This model is unavailable — click to configure"
            }
          >
            <span
              className={`model-dot${isAvailable ? "" : " model-dot-off"}`}
            />
            <span className="model-chip-label">{label}</span>
            <span className="model-chip-name">{displayModel}</span>
            <SlidersIcon size={13} />
          </Link>

          <button
            type="button"
            className="icon-button"
            onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
            aria-label={
              resolvedTheme === "dark"
                ? "Switch to light theme"
                : "Switch to dark theme"
            }
            title={
              resolvedTheme === "dark"
                ? "Switch to light theme"
                : "Switch to dark theme"
            }
          >
            {resolvedTheme === "dark" ? (
              <SunIcon size={16} />
            ) : (
              <MoonIcon size={16} />
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
