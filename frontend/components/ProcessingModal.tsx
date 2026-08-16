"use client";

import { useEffect, useRef, useState } from "react";
import { AlertIcon, ArrowRightIcon, CheckIcon } from "./Icons";

/**
 * Blocking modal shown while an assessment runs.
 *
 * On completion it does *not* auto-navigate: the user clicks "View report".
 * An automatic redirect after a long wait tends to yank the page away just as
 * someone looks back at the screen.
 */

export type ProcessingPhase = "running" | "done" | "error";

interface Props {
  phase: ProcessingPhase;
  modelName: string;
  isLocal: boolean;
  errorMessage?: string | null;
  onView: () => void;
  onDismiss: () => void;
}

const STEPS = [
  "Reading the report",
  "Matching risk factors",
  "Projecting to ages 25–45",
  "Writing recommendations",
];

export default function ProcessingModal({
  phase,
  modelName,
  isLocal,
  errorMessage,
  onView,
  onDismiss,
}: Props) {
  const [elapsed, setElapsed] = useState(0);
  const [step, setStep] = useState(0);
  const viewButtonRef = useRef<HTMLButtonElement>(null);

  // Elapsed timer. The real work gives no progress events, so this is the only
  // honest signal that something is still happening.
  useEffect(() => {
    if (phase !== "running") return;
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [phase]);

  // Advance the step display on a timer. These are indicative, not measured —
  // the API is a single call — so the last step is held rather than completing,
  // which would imply progress we cannot actually observe.
  useEffect(() => {
    if (phase !== "running") return;
    const interval = isLocal ? 9000 : 5000;
    const id = window.setInterval(() => {
      setStep((current) => Math.min(current + 1, STEPS.length - 1));
    }, interval);
    return () => window.clearInterval(id);
  }, [phase, isLocal]);

  // Move focus to the primary action when the run finishes.
  useEffect(() => {
    if (phase === "done") viewButtonRef.current?.focus();
  }, [phase]);

  // Escape dismisses only once the run has settled — cancelling mid-flight
  // would leave the request running with nowhere to deliver its result.
  useEffect(() => {
    if (phase === "running") return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onDismiss();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, onDismiss]);

  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const elapsedLabel =
    minutes > 0 ? `${minutes}m ${seconds}s` : `${seconds}s`;

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="processing-title"
    >
      <div className="modal">
        {phase === "running" && (
          <>
            <div className="spinner" />
            <h2 id="processing-title">Analysing report</h2>
            <p className="modal-note">
              Running on <code>{modelName}</code>.
              {isLocal
                ? " Local inference can take a few minutes."
                : " This usually takes 30–60 seconds."}
            </p>

            <div className="modal-steps">
              {STEPS.map((label, index) => (
                <div
                  key={label}
                  className={`modal-step${
                    index === step
                      ? " modal-step-on"
                      : index < step
                        ? " modal-step-done"
                        : ""
                  }`}
                >
                  <span className="modal-step-dot">
                    {index < step && <CheckIcon size={9} />}
                  </span>
                  {label}
                </div>
              ))}
            </div>

            <p className="modal-elapsed">Elapsed {elapsedLabel}</p>
          </>
        )}

        {phase === "done" && (
          <>
            <div className="modal-check">
              <CheckIcon size={26} />
            </div>
            <h2 id="processing-title">Report ready</h2>
            <p className="modal-note">
              Your risk projection is complete
              {elapsed > 0 ? ` (${elapsedLabel})` : ""}.
            </p>
            <button
              ref={viewButtonRef}
              type="button"
              className="btn btn-primary btn-lg btn-block"
              onClick={onView}
            >
              View report
              <ArrowRightIcon size={17} />
            </button>
          </>
        )}

        {phase === "error" && (
          <>
            <div
              className="modal-check"
              style={{ background: "var(--danger)" }}
            >
              <AlertIcon size={24} />
            </div>
            <h2 id="processing-title">Analysis failed</h2>
            <p className="modal-note">
              {errorMessage ?? "Something went wrong. Please try again."}
            </p>
            <button
              type="button"
              className="btn btn-secondary btn-block"
              onClick={onDismiss}
            >
              Back to form
            </button>
          </>
        )}
      </div>
    </div>
  );
}
