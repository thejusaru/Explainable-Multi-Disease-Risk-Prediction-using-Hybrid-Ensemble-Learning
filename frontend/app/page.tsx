"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import IntakeForm from "../components/IntakeForm";
import ReportUpload from "../components/ReportUpload";
import ProcessingModal, {
  type ProcessingPhase,
} from "../components/ProcessingModal";
import { AlertIcon, InfoIcon } from "../components/Icons";
import { ApiError, analyzeProfile, extractReport } from "../lib/api";
import { useAnalysis } from "../lib/analysis-store";
import { useSettings } from "../lib/settings";
import type { ExtractResponse, PatientProfile } from "../lib/types";

/**
 * Intake: upload → auto-fill → review → analyse.
 *
 * Extraction and analysis are separate calls so parsed values land in the form
 * where the user can correct them, rather than going straight to the model.
 */
export default function IntakePage() {
  const router = useRouter();
  const { engine, model } = useSettings();
  const { setResult } = useAnalysis();

  const [file, setFile] = useState<File | null>(null);
  const [extracting, setExtracting] = useState(false);
  const [extraction, setExtraction] = useState<ExtractResponse | null>(null);
  const [extractError, setExtractError] = useState<string | null>(null);

  const [phase, setPhase] = useState<ProcessingPhase | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  function describeError(err: unknown): string {
    if (err instanceof ApiError) return err.message;
    if (err instanceof TypeError) {
      // fetch() rejects with TypeError when the host is unreachable.
      return "Could not reach the API. Is the backend running on port 8000?";
    }
    return err instanceof Error ? err.message : "Something went wrong.";
  }

  async function handleFile(next: File | null) {
    setFile(next);
    setExtraction(null);
    setExtractError(null);

    if (!next) return;

    setExtracting(true);
    try {
      setExtraction(await extractReport(next));
    } catch (err) {
      setExtractError(describeError(err));
    } finally {
      setExtracting(false);
    }
  }

  async function handleAnalyse(profile: Partial<PatientProfile>) {
    setPhase("running");
    setAnalysisError(null);

    try {
      const response = await analyzeProfile(
        profile as PatientProfile,
        { engine: engine ?? undefined, model: model ?? undefined },
        {
          report_text: extraction?.report_text,
          image_base64: extraction?.image_base64,
          image_media_type: extraction?.image_media_type,
        },
      );
      setResult(response);
      setPhase("done");
    } catch (err) {
      setAnalysisError(describeError(err));
      setPhase("error");
    }
  }

  const isLocal = engine === "local";
  // With an image and no text, the vision model supplies the age during
  // analysis, so the form should not block on it.
  const ageOptional = Boolean(extraction?.image_base64);

  return (
    <main className="container">
      <div className="page-head">
        <h1>New risk assessment</h1>
        <p>
          Upload a medical report or enter details directly. Results project
          disease risk at ages 25, 30, 35, 40 and 45.
        </p>
      </div>

      <div className="steps">
        <div className={`step${file ? " step-done" : " step-active"}`}>
          <span className="step-num">1</span>
          Upload report
        </div>
        <span className="step-line" />
        <div className={`step${file ? " step-active" : ""}`}>
          <span className="step-num">2</span>
          Review details
        </div>
        <span className="step-line" />
        <div className="step">
          <span className="step-num">3</span>
          View report
        </div>
      </div>

      <div className="stack">
        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>Medical report</h2>
              <p>Optional — you can fill the form in by hand instead.</p>
            </div>
          </div>
          <div className="card-body">
            <ReportUpload
              file={file}
              onFile={handleFile}
              busy={phase === "running"}
              extracting={extracting}
              fieldsFound={extraction?.fields_found ?? []}
            />

            {extractError && (
              <div className="banner banner-danger" style={{ marginTop: 12 }}>
                <AlertIcon size={17} className="banner-icon" />
                <div>
                  <strong>Could not read that file</strong>
                  {extractError}
                </div>
              </div>
            )}

            {extraction?.requires_manual_entry && !extractError && (
              <div className="banner banner-warning" style={{ marginTop: 12 }}>
                <InfoIcon size={17} className="banner-icon" />
                <div>
                  <strong>Nothing pre-filled from this file</strong>
                  {extraction.notes.join(" ")}
                </div>
              </div>
            )}

            {extraction?.image_base64 && isLocal && (
              <div className="banner banner-danger" style={{ marginTop: 12 }}>
                <AlertIcon size={17} className="banner-icon" />
                <div>
                  <strong>Local models cannot read images</strong>
                  Switch to the cloud model in settings, or enter the values
                  manually below.
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="card">
          <div className="card-header">
            <div className="card-title-group">
              <h2>Patient details</h2>
              <p>
                {extraction?.fields_found?.length
                  ? "Highlighted fields were read from the report — correct anything wrong."
                  : "Fill in what you know. More detail gives a better estimate."}
              </p>
            </div>
          </div>
          <div className="card-body">
            <IntakeForm
              extracted={extraction?.profile ?? null}
              onSubmit={handleAnalyse}
              busy={phase === "running"}
              submitLabel="Analyse risk"
              ageOptional={ageOptional}
            />
          </div>
        </section>
      </div>

      {phase && (
        <ProcessingModal
          phase={phase}
          modelName={model ?? "the configured model"}
          isLocal={isLocal}
          errorMessage={analysisError}
          onView={() => router.push("/results")}
          onDismiss={() => setPhase(null)}
        />
      )}
    </main>
  );
}
