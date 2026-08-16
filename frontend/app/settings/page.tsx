"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { listEngines } from "../../lib/api";
import { useSettings, type ThemeChoice } from "../../lib/settings";
import type { EngineKind, EngineOption } from "../../lib/types";
import {
  AlertIcon,
  ArrowLeftIcon,
  CheckIcon,
  InfoIcon,
  MonitorIcon,
  MoonIcon,
  SunIcon,
} from "../../components/Icons";

/**
 * Model and appearance settings.
 *
 * Changes are staged locally and only committed on Save, so a mis-click does
 * not silently change which model analyses the next report. The one exception
 * is theme, which applies live — previewing a theme without applying it is
 * pointless, and it is trivially reversible.
 */
export default function SettingsPage() {
  const { engine, model, setEngineSelection, theme, setTheme, hydrated } =
    useSettings();

  const [engines, setEngines] = useState<EngineOption[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Staged (uncommitted) selection.
  const [draftEngine, setDraftEngine] = useState<EngineKind | null>(null);
  const [draftModel, setDraftModel] = useState<string | null>(null);
  const [justSaved, setJustSaved] = useState(false);

  useEffect(() => {
    let cancelled = false;

    listEngines()
      .then((response) => {
        if (cancelled) return;
        setEngines(response.engines);
        setLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setLoadError(
          "Could not reach the API. Start the backend, then reload this page.",
        );
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Seed the draft from saved settings once both have loaded.
  useEffect(() => {
    if (!hydrated) return;
    setDraftEngine(engine);
    setDraftModel(model);
  }, [hydrated, engine, model]);

  const dirty =
    draftEngine !== null &&
    (draftEngine !== engine || draftModel !== model);

  function selectEngine(option: EngineOption) {
    setDraftEngine(option.kind);
    // Keep the current model when re-selecting the same engine, so switching
    // away and back does not discard a chosen local model.
    setDraftModel(
      option.kind === draftEngine && draftModel ? draftModel : option.model,
    );
    setJustSaved(false);
  }

  function handleSave() {
    if (!draftEngine || !draftModel) return;
    setEngineSelection(draftEngine, draftModel);
    setJustSaved(true);
    window.setTimeout(() => setJustSaved(false), 2600);
  }

  function handleDiscard() {
    setDraftEngine(engine);
    setDraftModel(model);
    setJustSaved(false);
  }

  const activeDraft = engines.find((e) => e.kind === draftEngine);

  const themeOptions: {
    value: ThemeChoice;
    label: string;
    icon: React.ReactNode;
  }[] = [
    { value: "light", label: "Light", icon: <SunIcon size={17} /> },
    { value: "dark", label: "Dark", icon: <MoonIcon size={17} /> },
    { value: "system", label: "System", icon: <MonitorIcon size={17} /> },
  ];

  return (
    <main className="container">
      <div className="page-head">
        <Link href="/" className="btn btn-ghost" style={{ marginBottom: 10 }}>
          <ArrowLeftIcon size={15} />
          Back to assessment
        </Link>
        <h1>Settings</h1>
        <p>Choose which model analyses reports, and how the app looks.</p>
      </div>

      <div className="stack">
        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>Analysis model</h2>
              <p>Applies to every assessment run after you save.</p>
            </div>
          </div>
          <div className="card-body">
            {loadError ? (
              <div className="banner banner-danger">
                <AlertIcon size={17} className="banner-icon" />
                <div>
                  <strong>Cannot load models</strong>
                  {loadError}
                </div>
              </div>
            ) : loading ? (
              <p className="hint">Checking which models are available…</p>
            ) : (
              <>
                <div className="engine-grid">
                  {engines.map((option) => {
                    const isDraft = option.kind === draftEngine;
                    return (
                      <button
                        key={option.kind}
                        type="button"
                        className={`engine-card${isDraft ? " engine-card-on" : ""}`}
                        disabled={!option.available}
                        onClick={() => selectEngine(option)}
                        aria-pressed={isDraft}
                      >
                        {isDraft && (
                          <span className="engine-check">
                            <CheckIcon size={17} />
                          </span>
                        )}
                        <span className="engine-card-head">
                          <span className="engine-card-name">
                            {option.label}
                          </span>
                          {!option.available && (
                            <span className="badge-off">unavailable</span>
                          )}
                        </span>
                        <div className="engine-card-model">{option.model}</div>
                        <div className="engine-card-detail">
                          {option.detail}
                        </div>
                      </button>
                    );
                  })}
                </div>

                {/* Only the local engine has interchangeable models to pick. */}
                {activeDraft?.kind === "local" &&
                  activeDraft.models.length > 1 && (
                    <div className="field" style={{ marginTop: 18, maxWidth: 320 }}>
                      <label htmlFor="local-model">Local model</label>
                      <select
                        id="local-model"
                        value={draftModel ?? activeDraft.model}
                        onChange={(e) => {
                          setDraftModel(e.target.value);
                          setJustSaved(false);
                        }}
                      >
                        {activeDraft.models.map((name) => (
                          <option key={name} value={name}>
                            {name}
                          </option>
                        ))}
                      </select>
                      <span className="hint">
                        Larger models give better estimates but run slower.
                      </span>
                    </div>
                  )}

                {activeDraft?.kind === "local" && (
                  <div className="banner banner-warning" style={{ marginTop: 18 }}>
                    <AlertIcon size={17} className="banner-icon" />
                    <div>
                      <strong>Local models are less reliable</strong>
                      Smaller models produce less differentiated estimates,
                      cannot read images, and occasionally need a retry. Use the
                      cloud model for anything you intend to show someone.
                    </div>
                  </div>
                )}

                {engines.some((e) => !e.available) && (
                  <div className="banner banner-info" style={{ marginTop: 12 }}>
                    <InfoIcon size={17} className="banner-icon" />
                    <div>
                      {engines
                        .filter((e) => !e.available)
                        .map((e) => (
                          <div key={e.kind}>
                            <strong>{e.label} is unavailable</strong>
                            {e.detail}
                          </div>
                        ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>Appearance</h2>
              <p>Applies immediately and is remembered on this browser.</p>
            </div>
          </div>
          <div className="card-body">
            <div className="theme-options">
              {themeOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  className={`theme-option${
                    theme === option.value ? " theme-option-on" : ""
                  }`}
                  onClick={() => setTheme(option.value)}
                  aria-pressed={theme === option.value}
                >
                  {option.icon}
                  {option.label}
                </button>
              ))}
            </div>
          </div>
        </section>
      </div>

      <div className="save-bar">
        <span
          className={`save-status${
            dirty
              ? " save-status-dirty"
              : justSaved
                ? " save-status-saved"
                : ""
          }`}
        >
          {dirty ? (
            <>
              <AlertIcon size={15} />
              Unsaved changes
            </>
          ) : justSaved ? (
            <>
              <CheckIcon size={15} />
              Settings saved
            </>
          ) : (
            <>Model: {model ?? "not configured"}</>
          )}
        </span>

        <div className="btn-row">
          {dirty && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleDiscard}
            >
              Discard
            </button>
          )}
          <button
            type="button"
            className="btn btn-primary"
            onClick={handleSave}
            disabled={!dirty}
          >
            <CheckIcon size={16} />
            Confirm &amp; save
          </button>
        </div>
      </div>
    </main>
  );
}
