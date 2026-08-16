"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import AssessmentResults from "../../components/AssessmentResults";
import { ArrowLeftIcon, ClipboardIcon } from "../../components/Icons";
import { useAnalysis } from "../../lib/analysis-store";

/**
 * Dedicated report page.
 *
 * Reads the assessment from the shared store, which is backed by
 * sessionStorage — so a refresh here keeps the report rather than discarding a
 * result the user waited a minute for.
 */
export default function ResultsPage() {
  const router = useRouter();
  const { result, hydrated, clearResult } = useAnalysis();

  // Only redirect once the store has been read; redirecting before hydration
  // would bounce a user who landed here with a perfectly good stored result.
  useEffect(() => {
    if (hydrated && !result) router.replace("/");
  }, [hydrated, result, router]);

  if (!hydrated) {
    return (
      <main className="container">
        <p className="hint">Loading report…</p>
      </main>
    );
  }

  if (!result) {
    return (
      <main className="container">
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">
              <ClipboardIcon size={34} />
            </div>
            <h2>No report to show</h2>
            <p>Run an assessment to see a risk projection here.</p>
            <Link href="/" className="btn btn-primary">
              Start an assessment
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="container">
      <div className="page-head">
        <Link href="/" className="btn btn-ghost" style={{ marginBottom: 10 }}>
          <ArrowLeftIcon size={15} />
          Back to assessment
        </Link>
        <h1>Risk projection</h1>
        <p>
          Patient aged {result.assessment.profile.age}
          {result.assessment.profile.sex
            ? `, ${result.assessment.profile.sex}`
            : ""}{" "}
          · {result.assessment.conditions.length} condition(s) assessed
        </p>
      </div>

      <AssessmentResults result={result} />

      <div className="btn-row" style={{ marginTop: 22, justifyContent: "center" }}>
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => {
            clearResult();
            router.push("/");
          }}
        >
          Start a new assessment
        </button>
      </div>
    </main>
  );
}
